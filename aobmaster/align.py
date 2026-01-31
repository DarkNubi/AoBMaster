from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import AoBMasterError, ExitCode
from .pe import PEFile, Section


@dataclass(frozen=True)
class AlignedAnchor:
    path: Path
    anchor_fo: int
    anchor_rva: int
    anchor_va: int
    section_name: str
    drift_rva: int
    seed_hits: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "anchor": {"fo": hex(self.anchor_fo), "rva": hex(self.anchor_rva), "va": hex(self.anchor_va)},
            "section": self.section_name,
            "drift_rva": self.drift_rva,
            "seed_hits": self.seed_hits,
        }


def _scan_domain_ranges(pe: PEFile, *, mode: str, section: Section | None) -> list[tuple[int, bytes]]:
    if mode == "section":
        if not section:
            raise AoBMasterError(ExitCode.ALIGNMENT_FAILURE, "alignment_failed", "Missing section for section scan")
        return [(section.raw_ptr, pe.read_fo(section.raw_ptr, section.raw_size))]
    if mode == "module":
        ranges: list[tuple[int, bytes]] = []
        for s in pe.executable_sections():
            ranges.append((s.raw_ptr, pe.read_fo(s.raw_ptr, s.raw_size)))
        return ranges
    raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown scan domain: {mode}")


def align_versions(
    *,
    base_pe: PEFile,
    base_anchor_fo: int,
    base_anchor_rva: int,
    base_anchor_section: Section,
    version_paths: list[Path],
    mode: str,
    seed_bytes: int,
    seed_scan: str,
    seed_allow_multi: bool,
) -> list[AlignedAnchor]:
    out: list[AlignedAnchor] = []

    # Base anchor record (drift=0)
    out.append(
        AlignedAnchor(
            path=base_pe.path,
            anchor_fo=base_anchor_fo,
            anchor_rva=base_anchor_rva,
            anchor_va=base_pe.rva_to_va(base_anchor_rva),
            section_name=base_anchor_section.name,
            drift_rva=0,
            seed_hits=None,
        )
    )

    if not version_paths:
        return out

    if mode == "anchor-rva":
        for p in version_paths:
            pe = PEFile(p)
            anchor_rva = base_anchor_rva
            try:
                anchor_fo = pe.rva_to_fo(anchor_rva)
            except AoBMasterError as e:
                raise AoBMasterError(
                    ExitCode.ALIGNMENT_FAILURE,
                    "alignment_failed",
                    "Failed to resolve anchor RVA in version",
                    {"path": str(p), "anchor_rva": hex(anchor_rva), "cause": e.to_dict()},
                ) from e
            sec = pe.section_containing_rva(anchor_rva)
            if not sec:
                raise AoBMasterError(
                    ExitCode.ALIGNMENT_FAILURE,
                    "alignment_failed",
                    "Aligned RVA not within any section",
                    {"path": str(p), "anchor_rva": hex(anchor_rva)},
                )
            out.append(
                AlignedAnchor(
                    path=p,
                    anchor_fo=anchor_fo,
                    anchor_rva=anchor_rva,
                    anchor_va=pe.rva_to_va(anchor_rva),
                    section_name=sec.name,
                    drift_rva=0,
                    seed_hits=None,
                )
            )
        return out

    if mode != "bytespan":
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown alignment mode: {mode}")

    if seed_bytes <= 0:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "--seed-bytes must be > 0")

    if base_anchor_section.raw_size < seed_bytes:
        raise AoBMasterError(
            ExitCode.ALIGNMENT_FAILURE,
            "alignment_failed",
            "Seed longer than anchor section",
            {"seed_bytes": seed_bytes, "section": base_anchor_section.name},
        )

    half = seed_bytes // 2
    seed_start = base_anchor_fo - half
    seed_start = max(base_anchor_section.raw_ptr, seed_start)
    seed_start = min(seed_start, base_anchor_section.raw_ptr + base_anchor_section.raw_size - seed_bytes)
    seed = base_pe.read_fo(seed_start, seed_bytes)
    anchor_bias = base_anchor_fo - seed_start

    base_section_name = base_anchor_section.name
    for p in version_paths:
        pe = PEFile(p)
        if seed_scan == "section":
            sec = pe.section_by_name(base_section_name)
            if not sec:
                raise AoBMasterError(
                    ExitCode.ALIGNMENT_FAILURE,
                    "alignment_failed",
                    "Version missing base anchor section",
                    {"path": str(p), "section": base_section_name},
                )
            ranges = _scan_domain_ranges(pe, mode="section", section=sec)
        else:
            ranges = _scan_domain_ranges(pe, mode="module", section=None)

        # Exact seed scan (no wildcards)
        hits: list[int] = []
        for base_fo, buf in ranges:
            off = 0
            while True:
                idx = buf.find(seed, off)
                if idx < 0:
                    break
                hits.append(base_fo + idx)
                off = idx + 1

        if not hits:
            raise AoBMasterError(
                ExitCode.ALIGNMENT_FAILURE,
                "alignment_failed",
                "Seed bytespan not found in version",
                {"path": str(p)},
            )
        if (len(hits) > 1) and (not seed_allow_multi):
            raise AoBMasterError(
                ExitCode.ALIGNMENT_FAILURE,
                "alignment_failed",
                "Seed bytespan matched multiple times (seed-allow-multi=false)",
                {"path": str(p), "hits": len(hits)},
            )

        chosen_seed_fo = hits[0]
        anchor_fo = chosen_seed_fo + anchor_bias
        try:
            anchor_rva = pe.fo_to_rva(anchor_fo)
        except AoBMasterError as e:
            raise AoBMasterError(
                ExitCode.ALIGNMENT_FAILURE,
                "alignment_failed",
                "Failed to translate aligned anchor FO to RVA",
                {"path": str(p), "anchor_fo": hex(anchor_fo), "cause": e.to_dict()},
            ) from e
        sec2 = pe.section_containing_rva(anchor_rva)
        if not sec2:
            raise AoBMasterError(
                ExitCode.ALIGNMENT_FAILURE,
                "alignment_failed",
                "Aligned anchor not within any section",
                {"path": str(p), "anchor_fo": hex(anchor_fo)},
            )

        out.append(
            AlignedAnchor(
                path=p,
                anchor_fo=anchor_fo,
                anchor_rva=anchor_rva,
                anchor_va=pe.rva_to_va(anchor_rva),
                section_name=sec2.name,
                drift_rva=anchor_rva - base_anchor_rva,
                seed_hits=len(hits),
            )
        )

    return out
