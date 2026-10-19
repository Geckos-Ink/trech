#!/usr/bin/env python3
"""Encoded targets must export safe schemas and physical-unit held-out metrics."""
from pathlib import Path
import json
import math
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/torch'))
try:
    import numpy as np
except ImportError:
    print('SKIP: numpy unavailable')
    raise SystemExit(0)
from distill_discrete_scenario_operators import _make_run
from trech_torch.train_surrogate import main, predict_np, export_torchscript


def test_links():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        rows=lambda n: [{'x': float(x), 'drag': 10*math.exp(0.5*x), 'temperature':100+2*x}
                        for x in np.linspace(-2,2,n)]
        _make_run(root/'train',rows(90),'sample',50,1)
        _make_run(root/'test',rows(61),'sample',50,2)
        common=['--runs',str(root/'train'),'--validation-runs',str(root/'test'),
                '--source','hook_emits','--tag','sample','--expand','samples',
                '--inputs','x','--outputs','temperature,drag','--linear','--l2','0',
                '--out-json',str(root/'model.json'),'--manifest',str(root/'manifest.json')]
        assert main(common+['--log-outputs','drag']) == 0
        model=json.loads((root/'model.json').read_text())
        manifest=json.loads((root/'manifest.json').read_text())
        assert model['model']=='generic_surrogate_v2' and 'layers' not in model
        assert model['output_transforms']==['identity','exp']
        scalers=[np.asarray(model[key]) for key in ['input_mean','input_std','output_mean','output_std']]
        y=predict_np(np.array([[1.0]]),model['network']['layers'],scalers,model['output_transforms'])
        np.testing.assert_allclose(y,[[102,10*math.exp(0.5)]],atol=1e-10)
        assert manifest['metrics_holdout']['drag']['rmse'] < 1e-10
        assert manifest['metrics_units']=='decoded physical output units'
        # Existing models preserve the v1 wire format when no link is requested.
        assert main(common)==0
        legacy=json.loads((root/'model.json').read_text())
        assert legacy['model']=='generic_surrogate_v1' and 'layers' in legacy
        assert 'output_transforms' not in legacy
        invalid=False
        try:
            main(common+['--log-outputs','missing'])
        except SystemExit:
            invalid=True
        assert invalid
        data=rows(10);data[0]['drag']=0
        _make_run(root/'bad',data,'sample',50,3)
        bad=common.copy();bad[1]=str(root/'bad')
        invalid=False
        try:
            main(bad+['--log-outputs','drag'])
        except SystemExit:
            invalid=True
        assert invalid


def test_torchscript_links_when_available():
    try:
        import torch
    except ImportError:
        print("SKIP TorchScript link parity: torch unavailable")
        return
    with tempfile.TemporaryDirectory() as tmp:
        net=torch.nn.Linear(1,2)
        with torch.no_grad():
            net.weight.copy_(torch.tensor([[2.0],[0.5]])); net.bias.zero_()
        scalers=(np.array([0.]),np.array([1.]),np.array([100.,math.log(10)]),np.array([1.,1.]))
        target=Path(tmp)/'linked.pt'
        assert export_torchscript(net,scalers,target,['identity','exp'])
        result=torch.jit.load(str(target))(torch.tensor([[1.]])).detach().numpy()
        np.testing.assert_allclose(result,[[102,10*math.exp(0.5)]],rtol=1e-6)


if __name__=='__main__':
    test_links()
    test_torchscript_links_when_available()
    print('surrogate output links: PASS')
