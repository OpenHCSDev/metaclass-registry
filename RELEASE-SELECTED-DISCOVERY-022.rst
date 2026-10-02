Selected-discovery 0.2.2 release preparation
===========================================

Source/release coordination owner: Schrodinger. Parent owns installed acceptance
and explicit publication authorization. Draft source only, not a registry release.
Base main3294a69dabc9f99dd646c32571b8f97cc139d378 contains merged PR2.
Checked open metaclass PRs/issues: none; no competing release claimant found.
OpenHCS open PRs do not claim this metaclass version/minimum seam.

__version__ in src/metaclass_registry/__init__.py remains the sole release version
authority; original Hatch path in pyproject.toml reads it. This draft advances
that authority to0.2.2, following the original updater's next-patch convention.
No registry/discovery implementation, dependency roster or API fallback added.
No persisted formats change. Existing selected/full-discovery tests remain.

API/installer requirement
-------------------------

Merged OpenHCS376 calls LazyDiscoveryDict.discover_matching. Published0.2.1
predates that method, while OpenHCS currently permits >=0.2.1,<0.3. Therefore
an allowed normal-installer selection can lack the required API. The gitlink
3294a69 or a private wheel carrying version0.2.1 does not repair public version
identity. Paired OpenHCS draft requires >=0.2.2,<0.3 and pins this prepared source;
its minimum MUST NOT merge until the actual authorized0.2.2 artifact is available.

Source reproducer uses original v0.2.1 core source and actual package requirement:
the requirement admits0.2.1, that declaration lacks discover_matching; the draft
requirement rejects0.2.1, accepts0.2.2 and excludes0.3. No wheel download/install.
Merged PR2 owner/control/R0 history remains in the paired OpenHCS376 receipt.

Release order and authority
---------------------------

1. Review/merge this source version preparation normally.
2. Obtain explicit owner authorization to publish. Original scripts/release.py
   owns current-version/PyPI validation and annotated vVERSION tag publication;
   original .github/workflows/publish.yml owns Hatch build/twine/GitHub release
   and PyPI trusted publishing on a v* tag. No alternate publisher is introduced.
3. Authorized publisher verifies the exact merged source,0.2.2 wheel/sdist and
   required API, then runs the original release route. Do not invoke
   update_and_release.py here: it pushes main/rebases and would exceed this task.
4. Use OpenHCS's ORIGINAL scripts.wait_for_pypi_release.probe_release to verify
   exact-version metadata plus the ordinary installer index. Retain artifact
   hashes/import identity; metadata visibility alone is not API behavior proof.
5. Only after availability/API verification may parent integrate the coordinated
   OpenHCS minimum/gitlink and qualify a fresh normal installed retrieval route.

No tag push, workflow dispatch, artifact upload or publication authorization is
implied by this source PR. No private/backing install, new environment, native,
viewer, provider call or uncertain registration/input replay. Source checks use
the existing read-only Python, one CPU/512MiB/no swap/60s.

Existing optional verify_release_ready.py is not the publisher: source inspection
finds stale openhcs/setuptools metadata checks and PYPI_API_TOKEN assumptions,
while this package uses Hatch and the actual workflow uses trusted publishing.
Do not treat that optional helper as a completed release qualification. These
pre-existing helper defects are recorded for this release owner; no helper
mutation or build/download/cleanup side effect is attempted in this version draft.

NRA review MEMB-1/TIME-3: package declarations and original release mechanisms
remain authoritative, no mirrored manifests, compatibility aliases or ornamental
inheritance. Behavioral MRO/new-declaration evidence is unchanged from merged PR2;
this patch changes only the version declaration and changelog.

Published paired source/evidence
--------------------------------

Dependency draft https://github.com/OpenHCSDev/metaclass-registry/pull/3;
OpenHCS draft https://github.com/OpenHCSDev/openhcs/pull/414 (availability-gated).
Tested version source9d181724bf3eac9d06b6bd990312f722911c66fb; original pinned
R0 main3294a69 ->9d18172:24projections,zero positive,0.81s/44240KiB.
48source checks pass,0.87s/42372KiB: selected/full discovery, core and original
Hatch path-backed metadata authority. No discovery algorithm changed.
Original R0 tool3b03785f/Python3.14 unchanged; no copied guard/global R1 claim.

OpenHCS source witness invokes the original0.2.1 core declaration from tag commit
ca0a87e873f929b311a87a4d60cd3bfba315dbcf: actual AttributeError reports no
discover_matching. Its common imports resolve current source, so this narrow
missing-method control is not a fresh old-wheel/whole-package installation proof.
Actual old OpenHCS metadata admits0.2.1; the draft requires0.2.2. Original probe
reports candidate unavailable ("exact release is not visible yet"),0.35s/31904KiB.
Metadata-only HTTP read, no distribution downloaded. Do not merge minimum414.

Logs, exact command/resource receipts and reproducibility script are retained
under OpenHCS docs/validation/selected-discovery-release-022*. All three checks
serial under oneCPU/kernel512MiB/no-swap/60s, original read-only interpreters.
Resource startup warning RAM12.5GiB/home6.5GiB/root7.7GiB/swap10.2GiB; no new
worktrees/environments/builds. Releaser/package minimum remain declared owners,
not a new API roster. Optional readiness-helper source defects above remain
unqualified; original tag-triggered publisher stays intact and uninvoked.
