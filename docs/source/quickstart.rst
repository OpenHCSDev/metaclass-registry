Quick start guide
=================

Installation
------------

.. code-block:: bash

   python -m pip install metaclass-registry

Preferred nominal-family workflow
---------------------------------

Use ``RegistryFamily`` when subclasses register under the value of one semantic
class attribute. The root owns both the declaration and the resulting registry:

.. code-block:: python

   from metaclass_registry import AutoRegisterMeta, RegistryFamily

   class Plugin(metaclass=AutoRegisterMeta):
       __registry_family__ = RegistryFamily(
           "plugin_name",
           registry_name="plugin",
       )
       __registry__ = {}  # Local script: no package discovery required.
       plugin_name = None

   class EmailPlugin(Plugin):
       plugin_name = "email"

   class SMSPlugin(Plugin):
       plugin_name = "sms"

   assert Plugin.__registry__["email"] is EmailPlugin
   assert Plugin.__registry__["sms"] is SMSPlugin

An explicit plain registry is useful for a root declared in a one-file script.
Package-owned roots can omit ``__registry__`` to receive the library's lazy
discovery registry, whose package is inferred from the root's module.

``RegistryFamily.skip_if_no_key`` defaults to ``True``, so intermediate classes
without a key remain members of the nominal hierarchy but are not registry
entries. Descendants share the root's registry:

.. code-block:: python

   class DeliveryPlugin(Plugin):
       pass

   class PushPlugin(DeliveryPlugin):
       plugin_name = "push"

   assert DeliveryPlugin.__registry__ is Plugin.__registry__
   assert Plugin.__registry__["push"] is PushPlugin

Use ``RegistryKeyAttribute`` when the key axis is one of the library's shared
vocabulary values:

.. code-block:: python

   from metaclass_registry import RegistryKeyAttribute

   class Strategy(metaclass=AutoRegisterMeta):
       __registry_family__ = RegistryFamily(
           RegistryKeyAttribute.STRATEGY_LABEL,
           registry_name="strategy",
       )
       strategy_label = None

The low-level attributes ``__registry_key__``, ``__skip_if_no_key__``, and
``__registry_name__`` remain compatibility and introspection surfaces. New
ordinary roots should declare a ``RegistryFamily`` instead of repeating those
attributes manually.

.. _registryconfig-workflow:

Explicit RegistryConfig workflow
--------------------------------

Use ``RegistryConfig`` when registration requires an externally supplied
registry, derived keys, lazy discovery, secondary registries, or custom logging.
The nominal root owns the one authoritative configuration:

.. code-block:: python

   from metaclass_registry import (
       AutoRegisterMeta,
       RegistryConfig,
       make_suffix_extractor,
   )

   HANDLERS = {}
   HANDLER_CONFIG = RegistryConfig(
       registry_dict=HANDLERS,
       key_attribute="handler_type",
       key_extractor=make_suffix_extractor("Handler"),
       skip_if_no_key=True,
       registry_name="handler",
   )

   class Handler(metaclass=AutoRegisterMeta):
       __registry_config__ = HANDLER_CONFIG
       handler_type = None

   class ImageHandler(Handler):
       pass

   assert HANDLERS["image"] is ImageHandler

Secondary registries are derived indexes
----------------------------------------

Keep semantic membership in the primary registry. A ``SecondaryRegistry``
projects another class attribute under either the primary key or another named
attribute:

.. code-block:: python

   from metaclass_registry import PRIMARY_KEY, SecondaryRegistry

   METADATA_TYPES = {}

   class ImageMetadata:
       pass

   CONFIG = RegistryConfig(
       registry_dict=HANDLERS,
       key_attribute="handler_type",
       skip_if_no_key=True,
       secondary_registries=[
           SecondaryRegistry(
               registry_dict=METADATA_TYPES,
               key_source=PRIMARY_KEY,
               attr_name="metadata_type",
           )
       ],
       registry_name="handler",
   )

The supplied configuration is the authority for both indexes; do not manually
populate a second mapping with copied keys.

Next steps
----------

* See :doc:`api` for exact signatures.
* See :doc:`patterns` for registry selection guidance.
* See :doc:`examples` for discovery and caching examples.
