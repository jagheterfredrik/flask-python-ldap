import certifi
import ldap
from ldap.modlist import addModlist
from flask import current_app, _app_ctx_stack


def modify_modlist(oldAttrs, newAttrs):
    modifications = []
    oldKeySet = set(oldAttrs.keys())
    newKeySet = set(newAttrs.keys())
    for key in oldKeySet - newKeySet:
        modifications.append((ldap.MOD_DELETE, key, None))
    for key, newValue in newAttrs.items():
        oldValue = oldAttrs.get(key, [])
        if not newValue:
            modifications.append((ldap.MOD_DELETE, key, None))
        else:
            oldValueSet = set(oldValue)
            newValueSet = set(newValue)
            addList = list(newValueSet - oldValueSet)
            removeList = list(oldValueSet - newValueSet)
            if addList and removeList:
                # Minimize the number of values that needs to be transferred
                if len(addList + removeList) >= len(newValue):
                    modifications.append((ldap.MOD_REPLACE, key, newValue))
                else:
                    modifications.append((ldap.MOD_DELETE, key, removeList))
                    modifications.append((ldap.MOD_ADD, key, addList))
            elif addList:
                modifications.append((ldap.MOD_ADD, key, addList))
            elif removeList:
                modifications.append((ldap.MOD_DELETE, key, removeList))

    return modifications


class LDAP(object):

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.config.setdefault('LDAP_URI', 'ldap://localhost:389')
        app.config.setdefault('LDAP_BINDDN', None)
        app.config.setdefault('LDAP_SECRET', None)
        app.extensions['ldap'] = self
        app.teardown_appcontext(self.teardown)

    def connect(self):
        uri = current_app.config['LDAP_URI']
        conn = ldap.initialize(uri)
        if (uri.startswith('ldaps:')):
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT,ldap.OPT_X_TLS_DEMAND)
            # OPT_X_TLS_CACERTFILE does not work on OS X for some reason but validation seem to work
            try:
                conn.set_option(ldap.OPT_X_TLS_CACERTFILE, certifi.where())
            except ValueError:
                pass
            conn.set_option(ldap.OPT_X_TLS_NEWCTX,0)
        conn.simple_bind_s(current_app.config['LDAP_BINDDN'], current_app.config['LDAP_SECRET'])
        return conn

    def teardown(self, exception):
        ctx = _app_ctx_stack.top
        if hasattr(ctx, 'flask_ldap'):
            ctx.flask_ldap.unbind_s()

    @property
    def connection(self):
        ctx = _app_ctx_stack.top
        if ctx is not None:
            if not hasattr(ctx, 'flask_ldap'):
                ctx.flask_ldap = self.connect()
            return ctx.flask_ldap


class Attribute(object):

    def __init__(self, ldap_name, default=None, is_list=False):
        self.ldap_name = ldap_name
        self.default = default
        self.is_list = is_list


class BaseQuery(object):

    def __init__(self, model):
        self.model = model
        self._filter = None
        self._base = ldap.SCOPE_SUBTREE

    def _search(self):
        object_class_filter = ''.join([f'(objectclass={cls})' for cls in self.model.object_classes])
        if self._filter:
            full_filter = f'(&(&{object_class_filter}){self._filter})'
        else:
            full_filter = f'(&{object_class_filter})'
        try:
            return current_app.extensions['ldap'].connection.search_ext_s(
                self.model.base_dn,
                self._base,
                full_filter,
                attrlist=list(self.model._ldap_attrs)
            )
        except ldap.NO_SUCH_OBJECT:
            return []

    def filter(self, filter):
        self._filter = filter
        return self

    def base(self, base):
        self._base = base
        return self

    def all(self):
        return [self.model.from_search(*result) for result in self._search()]

    def first(self):
        res = self._search()
        return self.model.from_search(*res[0]) if res else None


class ModelBase(type):
    base_dn = None
    entry_rdn = 'cn'
    object_classes = ['top']

    def __init__(cls, name, bases, ns):
        _attr_defs = {}
        _ldap_attrs = set()
        attrs_to_delete = list()

        for base in bases:
            if hasattr(base, '_attr_defs'):
                _attr_defs.update(base._attr_defs)
            if hasattr(base, '_ldap_attrs'):
                _ldap_attrs.update(base._ldap_attrs)

        for key, value in ns.items():
            if isinstance(value, Attribute):
                _attr_defs[key] = value
                _ldap_attrs.add(value.ldap_name)
                attrs_to_delete.append(key)

        for key in attrs_to_delete:
            delattr(cls, key)

        cls._attr_defs = _attr_defs
        cls._ldap_attrs = _ldap_attrs

    @property
    def query(cls):
        return BaseQuery(cls)


class Entry(object, metaclass=ModelBase):

    def __init__(self, dn=None, new=True, **kwargs):
        attributes = {}
        _initial_attributes = {}
        for key, attr_def in self._attr_defs.items():
            value = kwargs.get(key)
            if value:
                _initial_attributes[key] = self.normalize_for_ldap(value)
            else:
                value = attr_def.default
            attributes[key] = self.normalize_for_ldap(value)
            if not dn and attr_def.ldap_name == self.entry_rdn:
                dn = f'{self.entry_rdn}={kwargs.get(key)},{self.base_dn}'

        object.__setattr__(self, '_attributes', attributes)
        self._initial_attributes = self.prep_attr_dict_for_ldap(_initial_attributes)

        self.dn = dn
        self.new = new

    @classmethod
    def from_search(cls, dn, attrs):
        parsed_attrs = {}
        for key, attr_def in cls._attr_defs.items():
            value = attrs.get(attr_def.ldap_name)
            if value is None:
                continue
            try:
                parsed_attrs[key] = [x.decode() for x in value]
            except UnicodeDecodeError:
                parsed_attrs[key] = value
        return cls(dn=dn, new=False, **parsed_attrs)

    @staticmethod
    def normalize_for_ldap(obj):
        if obj is None: return []
        return obj if isinstance(obj, list) else [str(obj)]

    @classmethod
    def prep_attr_dict_for_ldap(cls, d):
        attrs = {}
        for key, value in d.items():
            ldap_value = None
            if isinstance(value, list):
                ldap_value = [x.encode() for x in value if isinstance(x, str)]
            elif isinstance(value, str):
                ldap_value = [value.encode()] if value else None

            attr_def = cls._attr_defs[key]
            if ldap_value:
                if not attr_def.is_list and not any(ldap_value):
                    continue
                attrs[attr_def.ldap_name] = ldap_value
        return attrs

    def __getattr__(self, key):
        attributes = object.__getattribute__(self, '_attributes')
        if key in attributes:
            value = attributes[key]
            if not value:
                return [] if self._attr_defs[key].is_list else ''
            if not self._attr_defs[key].is_list and len(value) == 1:
                return value[0]
            else:
                return value
        return object.__getattribute__(self, key)

    def __setattr__(self, key, value):
        if key in self._attr_defs:
            self._attributes[key] = self.normalize_for_ldap(value)
        else:
            object.__setattr__(self, key, value)

    def __repr__(self):
        return str((self.dn, [(k, getattr(self, k)) for k in self._attributes.keys()]))

    def save(self):
        if self.new:
            add_attributes = self.prep_attr_dict_for_ldap(self._attributes)
            add_list = list({
                'objectclass': [x.encode() for x in self.object_classes],
                **add_attributes
            }.items())
            current_app.extensions['ldap'].connection.add_s(self.dn, add_list)
            self._initial_attributes = add_attributes
            self.new = False
        else:
            new_attributes = self.prep_attr_dict_for_ldap(self._attributes)
            mod_list = modify_modlist(self._initial_attributes, new_attributes)
            current_app.extensions['ldap'].connection.modify_s(self.dn, mod_list)
            self._initial_attributes = new_attributes
        return True

    def delete(self):
        try:
            current_app.extensions['ldap'].connection.delete_s(self.dn)
            self.new = True
            return True
        except:
            return False
