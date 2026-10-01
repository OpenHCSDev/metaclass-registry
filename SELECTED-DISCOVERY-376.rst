Declaration-selected discovery: OpenHCS376
==========================================

Owner: Schrodinger. Base448cdf07e0a0b513a9c9a8f67e896f601da11771.
Paired source repair: existing OpenHCS PR377, not a new knowledge implementation.

LazyDiscoveryDict owns locked partial admission. It delegates to the ORIGINAL
discover_registry_classes import/class-registration loop with a domain eligibility
hook. No second importer, registry, discovery cache, or complete-publication flag.
Selected import failures propagate; explicit full discovery retains its existing
semantics. Partial selection supports the existing flat discovery owner; custom
and recursive discovery are rejected explicitly rather than silently adapted.

New declared plugins enter through AutoRegisterMeta and remain exact same objects
when later full discovery admits the rest of the family. ImportError and ValueError
negative controls stay failures, not missing membership. Source tests use original
Python3.12 read-only environment; one CPU,512MiB/no swap,60s. Paired checks include
original knowledge regression and independent cooperative declarations before/after
the CellProfiler ancestor. First fixture did not declare __registry_config__ on its
root, so its child had no inherited registration authority: retained1fail/14pass.
Corrected to existing supported root declaration,50pass/1deselected in5.60s wall,
327192KiB; #379 custom-source test deliberately remains with Dewey.

IMPL-12/13 reuse one import mechanism; MEMB-1/2 retain original registration
authority. Python source projections in OpenHCS are selection eligibility, not
registered class/catalogue identities. No persisted format or installed environment
changes. Pinned R0 and final source checkpoint are recorded in paired PR377 receipt.
Parent/Dalton own installed knowledge retrieval and runtime acceptance.

Final productionf27ff1ce18ddeaaa6f9dff6ff10778d3f40bb94b. Original pinned R0
first rejects69b6's duplicated configuration admission; final owner factors one
_has_discovery_configuration for both scopes, removes repeated checks,31metric
projections zero-positive in1.68s/45356KiB. Final paired source selection53pass
in7.18s/343340KiB; stronger independent real-callable/cooperative hooks5pass
overlap that selection. Original rejected guard, test controls and broader
environment failures persist in OpenHCS selected-discovery-evidence, not waived.
OpenHCS production49b46d59e4eca9e5ea5c042c921f681bcf5ff732.

Ordinary main integration checkpoint
------------------------------------

Normal merge of dependency main34c3097ba449ba9501a5adb8d1e37a660652abaf
produces dc65ebe41459c2a85f2c80d84d7e238500e613d1. Production and tests
are byte-identical to22837a9; no dependency installs or private environments.
Original pinned R0 base34c3097 -> dc65ebe:31projections,zero positive,
exit0,1.31s/44376KiB. Pinned tool3b03785f and original Python3.14 owner,
not a detector copy. Evidence/commands are retained on original OpenHCS PR377
under docs/validation/selected-discovery-evidence/integration-*.
Paired OpenHCS normally merges current main33701725 into bbf2b784;
53focused source checks pass,7.22s/344260KiB, CPU0/512MiB/no swap/60s.
Independent real callable and genuine cooperative MRO cases are included.
OpenHCS R0:5177projections,zero positive,13.76s/86896KiB. Issue379 remains
Dewey-owned PR409; no canonical custom lookup implementation duplicated here.
Installed retrieval remains parent-owned while the author runtime is live.
