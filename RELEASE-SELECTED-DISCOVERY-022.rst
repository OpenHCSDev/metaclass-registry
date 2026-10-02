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
