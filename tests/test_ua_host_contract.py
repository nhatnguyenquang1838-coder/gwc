from pathlib import Path
import importlib.util, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('validate_ua_host_contract', ROOT/'tools/validate_ua_host_contract.py')
mod=importlib.util.module_from_spec(SPEC); sys.modules['validate_ua_host_contract']=mod; SPEC.loader.exec_module(mod)
class UAHostContractTests(unittest.TestCase):
    def test_contract_validates(self):
        self.assertTrue(mod.validate(ROOT)['valid'])
if __name__=='__main__': unittest.main()
