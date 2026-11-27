"""Closed identities for source-byte transport, never scientific admission.

The existing offset-0 entry is represented by None in speech_pinned_snapshot.
Only the single immutable offset-8 object below may select the CAS extension.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotProfile:
    name: str
    offset: int
    source_id: str
    source_role: str
    origin_main: str
    verify_run: int
    release_run: int | None
    artifact_id: int
    artifact_name: str
    zip_bytes: int
    zip_sha256: str
    admitted_source_sha256: str
    admission_path: str = ''
    admission_sha256: str = ''
    plan_path: str = ''
    plan_sha256: str = ''
    speakers: tuple[int, ...] = ()
    source_receipt_sha256: str = ''
    inner_bytes: int = 0
    inner_sha256: str = ''
    manifest_sha256: str = ''
    transport_tool_sha256: str = ''


SPATIAL = SnapshotProfile(
    name='spatial-offset8-v1', offset=8,
    source_id='librispeech-dev-clean-spatial-v1',
    source_role='original-LibriSpeech-fixed-spatial-source-revalidated',
    origin_main='21448956f65916577d13082e9dc58f275f8fbb70',
    verify_run=44281089122, release_run=None,
    artifact_id=14417923975,
    artifact_name='frontend-spatial-effects-44281089122',
    zip_bytes=470176194,
    zip_sha256='3b9a2419df9b8c1e5ba42bc24f20049e87fc28aeda6aa045d2f8f5f2b5be4cb2',
    admitted_source_sha256='f77a897bf9681af2c09f57515b99fb2d7ca072dc93371d438e872579e39f801e',
    admission_path='.github/research/frontend-evolution-v1/spatial-speech-admission-v1.json',
    admission_sha256='240c536fd70fee3152996b94fc69718fd8a687fdd30d3696d83a6e6c6a815524',
    plan_path='.github/research/frontend-evolution-v1/spatial-weights-v1.json',
    plan_sha256='f952a6ec0e0cadcae962eb93abc922bb311021687e827df7682fde112ec92767',
    speakers=(1673, 1919, 1988, 1993, 2035, 2078, 2086, 2277),
    source_receipt_sha256='4d05852bb839b18cf9f399d27adb66cb8907cf7cfb5780bb3a73e4185e7f8150',
    inner_bytes=470175417,
    inner_sha256='9e43c8847b4ccb9c4c073b7d03de5cd217bbef243996f34e982518febe62e525',
    manifest_sha256='970afa99922c4890fb9882aaf5212caa7cdbb105d80e526c3d3b9a81daf9d640',
    transport_tool_sha256='caef42bc30521fe56fb7020549c5ba30450f37ed7cb49628dd06694cbc1b061b',
)
CHOICES = (SPATIAL.name,)


def require_profile(profile: SnapshotProfile) -> SnapshotProfile:
    if profile is not SPATIAL:
        raise ValueError('UNREGISTERED_OR_MUTABLE_SOURCE_CACHE_PROFILE')
    return profile


def select(name: str | None) -> SnapshotProfile | None:
    if name is None:
        return None
    if name != SPATIAL.name:
        raise ValueError('UNREGISTERED_SOURCE_CACHE_PROFILE')
    return SPATIAL
