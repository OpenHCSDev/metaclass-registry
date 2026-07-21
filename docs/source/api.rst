API orientation
===============

``AutoRegisterMeta``
   Creates and populates a root ``__registry__`` from concrete subclass
   declarations.

``RegistryConfig``
   Configures the registry mapping, key attribute/extractor, discovery package,
   secondary registries, and logging.

``RegistryFamily`` and ``RegistryKeyAttribute``
   Declare the stable semantic key axis shared by a nominal family.

``RegisteredEnumMeta``
   Composes enum construction with nominal registration.

``LazyDiscoveryDict``
   Registry mapping that discovers a configured package on first read.

``SecondaryRegistry`` and ``SecondaryRegistryDict``
   Derived indexes populated from the primary declaration registry.

``RegistryCacheManager``
   Persists discovery metadata; it is not a second semantic registry.

The canonical import surface is ``metaclass_registry.__all__``.

Core declarations
-----------------

.. autoclass:: metaclass_registry.RegistryFamily
   :members:

.. py:class:: RegistryConfig(registry_dict, key_attribute, key_extractor=None, skip_if_no_key=False, secondary_registries=None, log_registration=True, registry_name="plugin", discovery_package=None, discovery_recursive=False, discovery_function=None)

   Explicit registration configuration passed to ``AutoRegisterMeta``.

   ``registry_dict`` is the authoritative target mapping and ``key_attribute``
   names the class attribute holding explicit keys. ``key_extractor`` can derive
   a key when that attribute is unset. Discovery, secondary indexes, and logging
   are configured by the remaining fields.

.. autoclass:: metaclass_registry.SecondaryRegistry
   :members:

.. autoclass:: metaclass_registry.LazyDiscoveryDict
   :members:

.. autofunction:: metaclass_registry.make_suffix_extractor
