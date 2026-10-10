#!/usr/bin/env python3
"""FE03 A2 source-only RealMAN metadata guards; no audio, DOA score or data admission.

Noncommercial research notice and deterministic native geometry are reviewed in
https://github.com/jiying2007/audio-pipeline/issues/693 .
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / ".github/research/frontend-evolution-v1/realman-source-metadata-d0.json"
DECISION = "REALMAN_SOURCE_METADATA_ONLY_DATA_NOT_ADMITTED"
DATA_REVISION = "fea47505cae8041f4b652b0954ba61c77d2b6df1"
CODE_REVISION = "9dc59f03a98149bc7fe5524d1363af83a5b399f7"
REQUIRED_CSV = ("filename", "real_st", "real_ed", "video_st", "video_ed",
                "angle(°)", "distance", "ele")
TEMPLATE_KEYS = {
    "schema_version", "experiment_id", "stage", "preregistration", "research_purpose",
    "decision", "data_execution_status", "shipping_authority", "data_bytes_admitted",
    "acoustic_accuracy_claim", "product_qualification", "raw_audio_redistribution",
    "university_notice", "aishell_notice", "effective_data_notice", "dataset_repo",
    "dataset_revision", "upstream_code_repo", "upstream_code_revision",
    "upstream_geometry_sources", "cohort_role", "source_partition",
    "recording_parent", "static_label_path", "moving_label_path", "selected_scene",
    "selected_static_utterance", "selected_moving_utterance", "selection_rule",
    "number_of_source_microphones", "raw_capture_sample_rate_hz",
    "target_sample_rate_hz", "nominal_label_rate_hz", "label_timebase_alignment",
    "csv_required_columns", "csv_optional_index_prefix", "channel_filename_convention",
    "physical_slot_map", "c2_profile", "c4_profile", "array_geometry",
    "requires_exact_csv_sha256", "requires_archive_sha256",
    "requires_four_identical_rate_channels", "requires_timestamp_alignment_before_doa",
    "no_new_workflow", "no_new_public_api"
}


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("FE03 A2 metadata: " + why)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_json(path: Path) -> dict:
    def distinct(items):
        o = {}
        for k, v in items:
            require(k not in o, "duplicate JSON key")
            o[k] = v
        return o

    def fail_constant(x):
        raise ValueError("nonfinite JSON " + x)

    result = json.loads(path.read_text(encoding="utf-8"),
                        object_pairs_hook=distinct, parse_constant=fail_constant)
    require(isinstance(result, dict), "JSON object expected")
    return result


def native_positions() -> tuple[tuple[float, float, float], ...]:
    # Independently transcribed/source-reviewed 32 physical coordinates.
    xyz = [(0.0, 0.0, 0.0)]
    for radius in (0.03, 0.06, 0.09):
        for i in range(8):
            phi = i * math.pi / 4
            xyz.append((radius * math.cos(phi), radius * math.sin(phi), 0.0))
    xyz += [(-0.12, 0.0, 0.0), (0.12, 0.0, 0.0), (0.15, 0.0, 0.0),
            (0.0, 0.0, 0.09), (0.0, 0.0, 0.045),
            (0.0, 0.0, -0.045), (0.0, 0.0, -0.09)]
    require(len(xyz) == 32, "wrong 32-channel geometry")
    return tuple(xyz)


def xy_rank(pos: tuple, ids: list[int]) -> int:
    p0 = pos[ids[0]]
    ds = [(pos[i][0]-p0[0], pos[i][1]-p0[1]) for i in ids[1:]]
    nonzero = [(x, y) for x, y in ds if math.hypot(x, y) > 1e-12]
    if not nonzero:
        return 0
    x, y = nonzero[0]
    for vx, vy in nonzero[1:]:
        if abs(x*vy-y*vx) > 1e-12*math.hypot(x, y)*math.hypot(vx, vy):
            return 2
    return 1


def aperture(pos: tuple, ids: list[int]) -> float:
    return max(math.dist(pos[i], pos[j]) for i in ids for j in ids)


def validate_contract(p: dict) -> dict:
    require(set(p) == TEMPLATE_KEYS, "machine contract field set drift")
    exact = {
        "schema_version": 1,
        "experiment_id": "FE03-A2-REALMAN-SOURCE-METADATA-D0",
        "stage": "frontend-evolution-v1",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/693#issuecomment-6091562243",
        "research_purpose": "NONCOMMERCIAL_RESEARCH_ONLY",
        "decision": DECISION,
        "data_execution_status": "PENDING_VERIFIED_CSV_ARCHIVE_AUDIO_AND_TIME_ALIGNMENT",
        "university_notice": "CC-BY-4.0",
        "aishell_notice": "CC-BY-NC-4.0",
        "effective_data_notice": "CC-BY-NC-4.0-NONCOMMERCIAL-RESEARCH",
        "dataset_repo": "AISHELL/RealMAN",
        "dataset_revision": DATA_REVISION,
        "upstream_code_repo": "Audio-WestlakeU/RealMAN",
        "upstream_code_revision": CODE_REVISION,
        "cohort_role": "disclosed-development",
        "source_partition": "val",
        "recording_parent": "val/ma_noisy_speech",
        "static_label_path": "val/val_static_source_location.csv",
        "moving_label_path": "val/val_moving_source_location.csv",
        "selected_scene": None,
        "selected_static_utterance": None,
        "selected_moving_utterance": None,
        "selection_rule": "LEXICALLY_LOWEST_VERIFIED_SHARED_SCENE_THEN_STATIC_MOVING_UTTERANCE_BEFORE_SCORES",
        "number_of_source_microphones": 32,
        "raw_capture_sample_rate_hz": 48000,
        "target_sample_rate_hz": 16000,
        "nominal_label_rate_hz": 10,
        "label_timebase_alignment": "UNVERIFIED_NO_TIMESTAMP_TO_AUDIO_CONVERSION",
        "csv_required_columns": list(REQUIRED_CSV),
        "csv_optional_index_prefix": "Unnamed:",
        "channel_filename_convention": "{record_stem}_CH{physical_index}.flac",
        "physical_slot_map": [1, 3, 5, 7],
    }
    require(all(p.get(k) == v and type(p.get(k)) is type(v)
                for k, v in exact.items()), "source/rights/timebase policy changed")
    for name in ("shipping_authority", "data_bytes_admitted", "acoustic_accuracy_claim",
                 "product_qualification", "raw_audio_redistribution"):
        require(p[name] is False, "research/source status promoted")
    for name in ("requires_exact_csv_sha256", "requires_archive_sha256",
                 "requires_four_identical_rate_channels",
                 "requires_timestamp_alignment_before_doa",
                 "no_new_workflow", "no_new_public_api"):
        require(p[name] is True, "missing fail-closed source guard")
    expected_sources = [
        {"path": "baselines/SSL/utils_.py",
         "blob_sha": "0f7554bbfd65f2c52a917526e277a264b325d102"},
        {"path": "baselines/SE/data_loaders/realman_enh_dataset.py",
         "blob_sha": "5847f807562a3a4bc3f3b614809ab4ca1d8c6959"},
    ]
    require(p["upstream_geometry_sources"] == expected_sources, "geometry code authority drift")
    expected_geom = {
        "central_physical_index": 0,
        "inner_ring_physical_indices": list(range(1, 9)),
        "middle_ring_physical_indices": list(range(9, 17)),
        "outer_ring_physical_indices": list(range(17, 25)),
        "ring_radii_m": [0.03, 0.06, 0.09],
        "inner_ring_angle_start_deg": 0,
        "inner_ring_step_deg": 45,
    }
    require(p["array_geometry"] == expected_geom, "physical geometry metadata changed")
    profiles = (
        ("c2_profile", "REALMAN_C2_INNER_OPPOSITE", [1, 5], 5, 1),
        ("c4_profile", "REALMAN_C4_INNER_CARDINAL", [1, 3, 5, 7], 15, 2),
    )
    pos = native_positions()
    for name, label, ids, mask, rank in profiles:
        expected = {"id": label, "physical_mic_ids": ids, "slot_active_mask": mask,
                    "expected_xy_rank": rank, "max_aperture_m": 0.06}
        require(p[name] == expected, "frozen subarray changed: " + name)
        require(xy_rank(pos, ids) == rank, "subarray XY rank mismatch")
        require(abs(aperture(pos, ids) - 0.06) < 1e-12, "unequal aperture")
    require(all(math.isfinite(v) for xyz in pos for v in xyz), "nonfinite source geometry")
    require(p["physical_slot_map"] == p["c4_profile"]["physical_mic_ids"],
            "source channel and adapter slot mismatch")
    return p


def authoritative_contract() -> dict:
    return validate_contract(read_json(CONTRACT))


def label_values(text: str, name: str, is_static: bool) -> tuple[float, ...]:
    require(bool(text) and len(text) <= 65536, "empty/unbounded label " + name)
    try:
        vals = tuple(float(s.strip()) for s in text.split(","))
    except ValueError as err:
        raise ValueError("non-numeric label " + name) from err
    require(bool(vals) and all(math.isfinite(x) for x in vals), "nonfinite label " + name)
    require(not is_static or len(vals) == 1, "static recording has moving labels")
    if name == "angle":
        require(all(-360. <= v <= 360. for v in vals), "angle outside source range")
    elif name == "distance":
        require(all(0. < v < 1e5 for v in vals), "nonpositive source distance")
    else:
        require(all(-90. <= v <= 90. for v in vals), "elevation outside source range")
    return vals


def parse_labels(data: bytes, family: str, p: dict) -> list[dict]:
    require(family in ("static", "moving"), "unknown source family")
    require(isinstance(data, bytes) and 0 < len(data) <= 64*1024*1024,
            "empty/unbounded CSV data")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        raise ValueError("non-UTF8 source labels") from err
    require("\x00" not in decoded, "NUL label data")
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    headers = reader.fieldnames or []
    require(all(isinstance(h, str) and bool(h) for h in headers),
            "nonstring/blank CSV header")
    require(len(headers) == len(set(headers)), "duplicate CSV header")
    require(set(REQUIRED_CSV).issubset(headers), "missing real-label fields")
    require(all(h in REQUIRED_CSV or h.startswith(p["csv_optional_index_prefix"])
                for h in headers), "unknown semantic label columns")
    rows, seen = [], set()
    for row in reader:
        require(len(rows) < 100000, "unbounded source rows")
        require(None not in row, "unexpected CSV extra fields")
        name = row["filename"]
        require(isinstance(name, str) and len(name) < 1024
                and name == name.strip() and "\\" not in name and "\x00" not in name
                and ":" not in name and not name.startswith("/"),
                "unsafe source file identity")
        path = PurePosixPath(name)
        expected_prefix = "VAL_S_" if family == "static" else "VAL_M_"
        require(name == path.as_posix() and ".." not in path.parts
                and path.suffix == ".flac" and len(path.parts) == 6
                and tuple(path.parts[:2]) == tuple(p["recording_parent"].split("/"))
                and path.parts[3] == family
                and path.name.startswith(expected_prefix)
                and re.fullmatch(r"[A-Za-z0-9_.-]+", path.name) is not None
                and "_CH" not in path.stem, "wrong source partition/family/file")
        require(name not in seen, "duplicate source identity")
        seen.add(name)
        stamps = {}
        for k in ("real_st", "real_ed", "video_st", "video_ed"):
            t = row[k] or ""
            require(re.fullmatch(r"[0-9]{1,18}", t) is not None,
                    "invalid/ambiguous source timestamp")
            stamps[k] = int(t)
        require(stamps["real_ed"] > stamps["real_st"]
                and stamps["video_ed"] > stamps["video_st"],
                "invalid sample/video interval")
        az = label_values(row["angle(°)"], "angle", family == "static")
        distance = label_values(row["distance"], "distance", family == "static")
        elevation = label_values(row["ele"], "elevation", family == "static")
        require(len(az) == len(distance) == len(elevation),
                "source label sequence count mismatch")
        rows.append({"filename": name, "scene": path.parts[2],
                     "family": family, "label_count": len(az),
                     "real_bounds": [stamps["real_st"], stamps["real_ed"]],
                     "video_bounds": [stamps["video_st"], stamps["video_ed"]],
                     "row_sha256": sha256(json.dumps(
                         {k: row[k] for k in REQUIRED_CSV},
                         ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8"))})
    require(bool(rows), "empty static/moving source label set")
    return rows


def physical_flac_paths(base: str, p: dict) -> tuple[str, ...]:
    require(isinstance(base, str) and base.endswith(".flac") and "_CH" not in base,
            "invalid utterance identity")
    stem = base[:-5]
    return tuple(stem + "_CH" + str(mic) + ".flac"
                 for mic in p["physical_slot_map"])


def preselect(static_rows: list[dict], moving_rows: list[dict],
              inventory: list[str], p: dict) -> dict:
    require(all(isinstance(x, str) for x in inventory)
            and len(inventory) == len(set(inventory)),
            "duplicate/untrusted inventory paths")
    available = set(inventory)

    def eligible(rows):
        return sorted((row for row in rows if
                       set(physical_flac_paths(row["filename"], p)).issubset(available)),
                      key=lambda row: row["filename"])

    static, moving = eligible(static_rows), eligible(moving_rows)
    scenes = sorted(set(row["scene"] for row in static) &
                    set(row["scene"] for row in moving))
    require(bool(scenes), "no shared static/moving scene with all four channels")
    scene = scenes[0]
    s = next(row for row in static if row["scene"] == scene)
    m = next(row for row in moving if row["scene"] == scene)
    return {"scene": scene, "static_file": s["filename"],
            "moving_file": m["filename"], "physical_slot_map": p["physical_slot_map"],
            "decision": "PROVISIONAL_INVENTORY_ONLY_AUDIO_NOT_ADMITTED",
            "no_acoustic_scores": True, "shipping_authority": False}


def self_test() -> None:
    p = authoritative_contract()
    head = list(REQUIRED_CSV)
    def fixture(file, a, d, e):
        return {"filename": file, "real_st": "4800", "real_ed": "9600",
                "video_st": "5000", "video_ed": "10000",
                "angle(°)": a, "distance": d, "ele": e}
    def csv_bytes(rows, headers=head):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode("utf-8")
    sname = "val/ma_noisy_speech/Gym/static/P0001/VAL_S_GYM_P0001_0001.flac"
    mname = "val/ma_noisy_speech/Gym/moving/P0001/VAL_M_GYM_P0001_0002.flac"
    static = csv_bytes([fixture(sname, "30", "1.3", "0")])
    moving = csv_bytes([fixture(mname, "30,35", "1.3,1.4", "0,0")])
    ss = parse_labels(static, "static", p)
    mm = parse_labels(moving, "moving", p)
    # A label receipt must bind all semantic metadata, including source
    # and video timestamps, not only the angle/distance/elevation fields.
    for field, edited in (("real_st", "4801"), ("video_st", "5001"),
                          ("angle(°)", "31")):
        changed = fixture(sname, "30", "1.3", "0")
        changed[field] = edited
        observed = parse_labels(csv_bytes([changed]), "static", p)
        require(observed[0]["row_sha256"] != ss[0]["row_sha256"],
                "semantic label or source-clock tamper retained original digest")
    inventory = list(physical_flac_paths(sname,p) + physical_flac_paths(mname,p))
    chosen = preselect(ss, mm, inventory, p)
    require(chosen["scene"] == "Gym" and chosen["static_file"] == sname
            and chosen["moving_file"] == mname
            and chosen["no_acoustic_scores"] is True,
            "metadata-only selection not deterministic")
    defects = (
        lambda q: q.update(data_bytes_admitted=True),
        lambda q: q.update(shipping_authority=True),
        lambda q: q.update(research_purpose="COMMERCIAL_SHIPPING"),
        lambda q: q.update(dataset_revision="0"*40),
        lambda q: q.update(label_timebase_alignment="VERIFIED"),
        lambda q: q.update(physical_slot_map=[0,1,2,3]),
        lambda q: q["array_geometry"].update(ring_radii_m=[0.035,0.06,0.09]),
        lambda q: q["c4_profile"].update(expected_xy_rank=1),
        lambda q: q.update(static_label_path="train/train_static_source_location.csv"),
    )
    for change in defects:
        candidate = copy.deepcopy(p)
        change(candidate)
        try:
            validate_contract(candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("mutated source authority accepted")
    invalid_csv = (
        csv_bytes([fixture(sname,"NaN","1.3","0")]),
        csv_bytes([fixture(sname,"30,40","1.3","0")]),
        csv_bytes([fixture(sname.replace("Gym/static","Gym/moving"),"30","1.3","0")]),
        csv_bytes([fixture(sname.replace("val/","train/"),"30","1.3","0")]),
        csv_bytes([fixture(sname,"30","-1","0")]),
        csv_bytes([dict(fixture(sname,"30","1.3","0"),real_ed="100")]),
        csv_bytes([fixture(sname,"30","1.3","0"),fixture(sname,"30","1.3","0")]),
        csv_bytes([fixture(sname,"30","1.3","0")],headers=head + ["surprise"]),
        csv_bytes([fixture(sname,"30","1.3","0")],headers=head + ["filename"]),
        csv_bytes([fixture(sname.replace("/Gym/","/../"),"30","1.3","0")]),
        csv_bytes([fixture(sname.replace("VAL_S_GYM","VAL_M_GYM"),"30","1.3","0")]),
        csv_bytes([fixture(sname.replace("/Gym/static/","/Gym/static/./"),"30","1.3","0")]),
        csv_bytes([fixture(sname.replace("/Gym/static/","/Gym/static//"),"30","1.3","0")]),
        csv_bytes([fixture(sname.replace("/P0001/","/P0001/extra/"),"30","1.3","0")]),
        csv_bytes([fixture(sname.replace(".flac",".FLAC"),"30","1.3","0")]),
    )
    for payload in invalid_csv:
        try:
            parse_labels(payload, "static", p)
        except (ValueError, csv.Error):
            pass
        else:
            raise AssertionError("invalid source label file accepted")
    for bad in ([], physical_flac_paths(sname,p),
                list(inventory) + [inventory[0]]):
        try:
            preselect(ss,mm,list(bad),p)
        except ValueError:
            pass
        else:
            raise AssertionError("incomplete/duplicate inventory accepted")
    report = {
        "status": "REALMAN_METADATA_D0_SELF_TEST_PASS",
        "decision": DECISION, "data_bytes_admitted": False,
        "experimental_doa_scores": False,
        "upstream_revision": CODE_REVISION,
        "dataset_revision": DATA_REVISION,
        "c2_mask": p["c2_profile"]["slot_active_mask"],
        "c4_mask": p["c4_profile"]["slot_active_mask"],
        "static_rows_tested": len(ss), "moving_rows_tested": len(mm),
        "authority_mutations_rejected": len(defects),
        "csv_negatives_rejected": len(invalid_csv),
        "inventory_negatives_rejected": 3,
        "contract_sha256": sha256(CONTRACT.read_bytes()),
    }
    print(json.dumps(report,sort_keys=True))


def main() -> int:
    cli=argparse.ArgumentParser()
    cli.add_argument("--self-test", action="store_true")
    cli.add_argument("--check", action="store_true")
    a=cli.parse_args()
    require(a.self_test != a.check, "specify exactly one of --self-test or --check")
    if a.self_test:
        self_test()
    else:
        p=authoritative_contract()
        print(json.dumps({
            "decision": DECISION, "research_purpose": p["research_purpose"],
            "dataset_revision": p["dataset_revision"],
            "metadata_schema": "SOURCE_ONLY",
            "audio_bytes_admitted": False,
            "doa_measured": False,
            "contract_sha256": sha256(CONTRACT.read_bytes())
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
