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
        net=torch.nn.Linear(1,3)
        with torch.no_grad():
            net.weight.copy_(torch.tensor([[2.0],[0.5],[0.8]])); net.bias.zero_()
        scalers=(np.array([0.]),np.array([1.]),np.array([100.,math.log(10),-.4]),np.array([1.,1.,1.]))
        target=Path(tmp)/'linked.pt'
        assert export_torchscript(net,scalers,target,['identity','exp','sigmoid'])
        result=torch.jit.load(str(target))(torch.tensor([[1.]])).detach().numpy()
        np.testing.assert_allclose(result,[[102,10*math.exp(0.5),1/(1+math.exp(-.4))]],rtol=1e-6)
        # A saturated fraction is valid, but a non-finite encoded value is not.
        fraction=torch.nn.Linear(1,1)
        with torch.no_grad():
            fraction.weight.fill_(1);fraction.bias.zero_()
        path=Path(tmp)/'fraction.pt'
        assert export_torchscript(fraction,(np.array([0]),np.array([1]),np.array([0]),np.array([2])),path,['sigmoid'])
        loaded=torch.jit.load(str(path))
        np.testing.assert_array_equal(loaded(torch.tensor([[-1000.],[1000.]])).detach().numpy(),[[0.],[1.]])
        assert not np.isfinite(loaded(torch.tensor([[float('inf')]])).detach().numpy()).all()


def test_logit_links():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        def rows(n):
            return [{'x':float(x),'p':1/(1+math.exp(-(.8*x-.4))),
                     'positive':math.exp(.2*x),'raw':3*x+2} for x in np.linspace(-4,4,n)]
        _make_run(root/'train',rows(80),'sample',50,1)
        _make_run(root/'test',rows(41),'sample',50,2)
        common=['--runs',str(root/'train'),'--validation-runs',str(root/'test'),
                '--source','hook_emits','--tag','sample','--expand','samples',
                '--inputs','x','--outputs','p,positive,raw','--linear','--l2','0',
                '--out-json',str(root/'model.json'),'--manifest',str(root/'manifest.json')]
        assert main(common+['--logit-outputs','p','--log-outputs','positive'])==0
        model=json.loads((root/'model.json').read_text())
        manifest=json.loads((root/'manifest.json').read_text())
        assert model['model']==manifest['model']=='generic_surrogate_v2'
        assert model['output_transforms']==manifest['output_transforms']==['sigmoid','exp','identity']
        assert manifest['metrics_holdout']['p']['rmse']<1e-14
        scalers=[np.asarray(model[key]) for key in ['input_mean','input_std','output_mean','output_std']]
        actual=predict_np(np.array([[1.]]),model['network']['layers'],scalers,model['output_transforms'])
        np.testing.assert_allclose(actual,[[1/(1+math.exp(-.4)),math.exp(.2),5]],atol=1e-14)
        # Sigmoid decoding itself never evaluates a positive exponential.
        with np.errstate(over='raise',invalid='raise'):
            bounds=predict_np(np.array([[-1000.],[1000.]]),
                [{'weights':[[1.]],'bias':[0.],'activation':'none'}],
                (np.array([0.]),np.array([1.]),np.array([0.]),np.array([1.])),['sigmoid'])
        np.testing.assert_array_equal(bounds,[[0.],[1.]])
        for flags in (['--logit-outputs','missing'],
                      ['--logit-outputs','p','--log-outputs','p']):
            try:
                main(common+flags)
            except SystemExit:
                pass
            else:
                raise AssertionError('invalid logit declaration accepted')
        for value in (0.,1.,-.1,1.1,float('nan')):
            bad=rows(12);bad[0]['p']=value
            _make_run(root/'bad',bad,'sample',50,3)
            for split in ('--runs','--validation-runs'):
                changed=common.copy();changed[changed.index(split)+1]=str(root/'bad')
                try:
                    main(changed+['--logit-outputs','p'])
                except SystemExit:
                    pass
                else:
                    raise AssertionError(f'logit fit silently accepted {value} in {split}')


if __name__=='__main__':
    test_links()
    test_logit_links()
    test_torchscript_links_when_available()
    print('surrogate output links: PASS')
