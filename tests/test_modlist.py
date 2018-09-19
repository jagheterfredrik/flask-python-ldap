import ldap
from flask_python_ldap import modify_modlist

def test_modlist():
    old = {
        'remove_all': ['a'],
        'add_one': ['a', 'b'],
        'remove_one': ['a', 'b'],
        'replace_one': ['a'],
        'replace_all': ['a', 'b'],
        'replace_some': ['a', 'b'],
        'replace_minority': ['a', 'b', 'c'],
    }
    new = {
        'remove_all': [],
        'add_one': ['a', 'b', 'c'],
        'remove_one': ['a'],
        'replace_one': ['b'],
        'replace_all': ['c', 'd'],
        'replace_some': ['b', 'c'],
        'replace_minority': ['a', 'b', 'd'],
    }
    mod_list = modify_modlist(old, new)
    for mod_entry in mod_list:
        mod, attr, value = mod_entry
        if attr == 'remove_all':
            assert mod == ldap.MOD_DELETE
            assert value == None
        elif attr == 'add_one':
            assert mod == ldap.MOD_ADD
            assert value == ['c']
        elif attr == 'remove_one':
            assert mod == ldap.MOD_DELETE
            assert value == ['b']
        elif attr == 'replace_one':
            assert mod == ldap.MOD_REPLACE
            assert value == ['b']
        elif attr == 'replace_all':
            assert mod == ldap.MOD_REPLACE
            assert value == ['c', 'd']
        elif attr == 'replace_some':
            assert mod == ldap.MOD_REPLACE
            assert value == ['b', 'c']
        elif attr == 'replace_minority':
            assert mod in [ldap.MOD_DELETE, ldap.MOD_ADD]
            assert value in [['c'], ['d']]
        else:
            assert False, 'A modification was not accounted for'
