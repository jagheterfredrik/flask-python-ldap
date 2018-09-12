import ldap
from ldap.modlist import addModlist, modifyModlist
from flask import current_app, _app_ctx_stack


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
            conn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
            conn.set_option(ldap.OPT_X_TLS_DEMAND, True)
        else:
            conn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_NEVER)
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
            conn.set_option(ldap.OPT_X_TLS_DEMAND, False)
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

    def _search(self, limit=0):
        object_class_filter = ''.join([f'(objectclass={cls})' for cls in self.model.object_classes])
        if self._filter:
            full_filter = f'(&(&{object_class_filter}){self._filter})'
        else:
            full_filter = f'(&{object_class_filter})'
        try:
            return current_app.extensions['ldap'].connection.search_ext_s(
                self.model.base_dn,
                ldap.SCOPE_SUBTREE,
                full_filter,
                attrlist=list(self.model._ldap_attrs),
                sizelimit=limit
            )
        except ldap.NO_SUCH_OBJECT:
            return []

    def filter(self, filter):
        self._filter = filter
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
        cls._attr_defs = {}
        cls._ldap_attrs = set()

        for key, value in ns.items():
            if isinstance(value, Attribute):
                cls._attr_defs[key] = value
                cls._ldap_attrs.add(value.ldap_name)

        for key in cls._attr_defs.keys():
            delattr(cls, key)

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

    def __delattr__(self, key):
        if key not in self._attributes:
            raise AttributeError('no such attribute')
        self._attributes[key] = None

    def __repr__(self):
        return str((self.dn, [(k, getattr(self, k)) for k in self._attributes.keys()]))

    def save(self):
        if self.new:
            add_list = list({
                'objectclass': [x.encode() for x in self.object_classes],
                **self.prep_attr_dict_for_ldap(self._attributes)
            }.items())
            current_app.extensions['ldap'].connection.add_s(self.dn, add_list)
        else:
            new_attributes = self.prep_attr_dict_for_ldap(self._attributes)
            mod_list = modifyModlist(self._initial_attributes, new_attributes)
            current_app.extensions['ldap'].connection.modify_s(self.dn, mod_list)
        return True

    def delete(self):
        try:
            current_app.extensions['ldap'].connection.delete_s(self.dn)
            self.new = True
            return True
        except:
            return False
