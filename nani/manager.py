from django.db import models
from django.db.models.query import QuerySet
from django.db.models.query_utils import Q
from django.utils.translation import get_language
from nani.utils import R, combine

class FieldTranslator(dict):
    """
    Translates *shared* field names from '<shared_field>' to
    'master__<shared_field>' and caches those names.
    """
    def __init__(self, manager):
        self.manager = manager
        self.shared_fields = tuple(self.manager.model._meta.get_all_field_names())
        self.translated_fields  = tuple(self.manager.translations_model._meta.get_all_field_names())
        super(FieldTranslator, self).__init__()
        
    def get(self, key):
        if not key in self:
            self[key] = self.build(key)
        return self[key]
    
    def build(self, key):
        if key.startswith(self.shared_fields):
            return 'master__%s' % key
        else:
            return key


class TranslationManager(models.Manager):
    """
    Manager class for models with translated fields
    """
    def __init__(self):
        self._local_field_names = None
        self._field_translator = None
        super(TranslationManager, self).__init__()

    #===========================================================================
    # Helpers and properties 
    #===========================================================================

    @property
    def translations_manager(self):
        """
        Get manager of translations model
        """
        return self.translations_model.objects
    
    @property
    def translations_accessor(self):
        """
        Get the name of the reverse FK from the shared model
        """
        return self.model._meta.translations_accessor
    
    @property
    def translations_model(self):
        """
        Get the translations model class
        """
        return self.model._meta.translations_model
        
    @property
    def field_translator(self):
        """
        Field translator for this manager
        """
        if self._field_translator is None:
            self._field_translator = FieldTranslator(self)
        return self._field_translator
        
    @property
    def local_field_names(self):
        if self._local_field_names is None:
            self._local_field_names = self.model._meta.get_all_field_names()
        return self._local_field_names

    def _recurse_q(self, q):
        """
        Recursively translate fieldnames in a Q object.
        
        TODO: What happens if we span multiple relations?
        """
        newchildren =  []
        for child in q.children:
            if isinstance(child, R):
                newchildren.append(child)
            elif isinstance(child, Q):
                newq = self._recurse_q(child)
                newchildren.append(self._recurse_q(newq))
            else:
                key, value = child
                newchildren.append((self.field_translator.get(key), value))
        q.children = newchildren
        return q
    
    #===========================================================================
    # Queryset/Manager API 
    #===========================================================================
    
    def get_queryset(self):
        """
        Make sure that querysets inherit the methods on this manager (chaining)
        """
        qs = super(TranslationManager, self).get_queryset()
        bases = [QuerySet, TranslationManager]
        new_queryset_cls = type('TranslationManagerQueryset', tuple(bases), {})
        qs.__class__ = new_queryset_cls
        return qs
        
    def create(self, **kwargs):
        """
        When we create an instance, what we actually need to do is create two
        separate instances: One shared, and one translated.
        For this, we split the 'kwargs' into translated and shared kwargs
        and set the 'master' FK from in the translated kwargs to the shared
        instance.
        If 'language_code' is not given in kwargs, set it to the current
        language.
        """
        tkwargs = {}
        for key in kwargs.keys():
            if not key in self.local_field_names:
                tkwargs[key] = kwargs.pop(key)
        # Enforce the language_code kwarg
        if 'language_code' not in tkwargs:
            tkwargs['language_code'] = get_language()
        # Allow a pre-existing master to be passed, but only if no shared fields
        # are given.
        if 'master' in tkwargs:
            if kwargs:
                raise RuntimeError(
                    "Cannot explicitly use a master (shared) instance and shared fields in create"
                )
        else:
            # create shared instance
            shared = super(TranslationManager, self).create(**kwargs)
            tkwargs['master'] = shared
        # create translated instance
        trans = self.translations_model.objects.create(**tkwargs)
        # return combined instance
        return combine(trans)
    
    def get(self, *args, **kwargs):
        """
        Get an object by querying the translations model and returning a 
        combined instance.
        """
        # Enforce a language_code to be used
        if not 'language_code' in kwargs:
            kwargs['language_code'] = get_language()
        # Translated kwargs from '<shared_field>' to 'master__<shared_field>'
        # where necessary.
        newkwargs = {}
        for key, value in kwargs.items():
            newkwargs[self.field_translator.get(key)] = value
        # Translate args (Q objects) from '<shared_field>' to
        # 'master_<shared_field>' where necessary.
        newargs = []
        for q in args:
            newargs.append(self._recurse_q(q))
        # Enforce 'select related' onto 'mastser'
        qs = self.translations_manager.select_related('master')
        # Get the translated instance
        trans = qs.get(*newargs, **newkwargs)
        # Return a combined instance
        return combine(trans)

    def aggregate(self, *args, **kwargs):
        raise NotImplementedError()

    def latest(self, field_name=None):
        raise NotImplementedError()

    def in_bulk(self, id_list):
        raise NotImplementedError()

    def delete(self):
        raise NotImplementedError()
    delete.alters_data = True

    def update(self, **kwargs):
        raise NotImplementedError()
    update.alters_data = True

    def values(self, *fields):
        raise NotImplementedError()

    def values_list(self, *fields, **kwargs):
        raise NotImplementedError()

    def dates(self, field_name, kind, order='ASC'):
        raise NotImplementedError()

    def filter(self, *args, **kwargs):
        raise NotImplementedError()

    def exclude(self, *args, **kwargs):
        raise NotImplementedError()

    def complex_filter(self, filter_obj):
        raise NotImplementedError()

    def annotate(self, *args, **kwargs):
        raise NotImplementedError()

    def order_by(self, *field_names):
        raise NotImplementedError()

    def reverse(self):
        raise NotImplementedError()

    def defer(self, *fields):
        raise NotImplementedError()

    def only(self, *fields):
        raise NotImplementedError()
    
    def __iter__(self):
        for obj in super(TranslationManager, self):
            yield combine(obj)