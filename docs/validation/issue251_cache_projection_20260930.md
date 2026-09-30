# Non-creating projection from the existing cache path owner

OpenHCS issue251 must admit native startup cache writes before spawning.
`get_cache_file_path(..., create=False)` projects the canonical owner-resolved
cache destination without mkdir, keeping XDG/default authority here. Existing
creating callers are unchanged; no second path/default registry.

Source regression verifies identical projected/creating paths and no directory
creation during projection (included in62-pass paired source shard). No install
or native runtime. Paired OpenHCS draft references
https://github.com/OpenHCSDev/openhcs/issues/251; parent owns integration.
