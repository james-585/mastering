"""STORY-008 Integration Guide: Code Changes Required

This file documents the specific code changes needed to integrate stem separation
into the existing pipeline.py and cli.py modules.

═══════════════════════════════════════════════════════════════════════════════
1. ERRORS.PY — Add DependencyError
═══════════════════════════════════════════════════════════════════════════════

File: suno_mastering/errors.py

Add this class after TargetsLoadError:

    class DependencyError(MasteringError):
        \"\"\"Raised when an optional dependency (e.g. demucs, torch) is required
        for a requested feature (e.g. --split-stems) but is not installed.
        
        STORY-008: Used by io.stem_separation when demucs/torch are missing,
        providing actionable pip install instructions rather than letting a raw
        ModuleNotFoundError propagate to the CLI.
        \"\"\"

═══════════════════════════════════════════════════════════════════════════════
2. CONFIG.PY — Add StemConfig
═══════════════════════════════════════════════════════════════════════════════

File: suno_mastering/config.py

Add this dataclass after the imports:

    @dataclass
    class StemConfig:
        \"\"\"Configuration for stem-separated pre-mastering (STORY-008).
        
        Controls the optional AI stem-separation pipeline stage that runs before
        Stage 1 (measure_all). When enabled via --split-stems, the input audio is
        split into four stems (vocals, drums, bass, other), targeted DSP is applied,
        then stems are re-summed before entering the main pipeline.
        \"\"\"
        enabled: bool = False
        model_name: str = "htdemucs"  # "htdemucs" | "htdemucs_ft" | "mdx_extra"
        
        # Bass stem processing
        bass_mono_cutoff_hz: float = 90.0  # Mono summing below this frequency
        
        # Vocal stem processing  
        vocal_lpf_hz: float = 15000.0      # Low-pass to remove AI sizzle
        vocal_hpf_hz: float = 80.0         # High-pass to remove rumble/DC

Then, in the MasteringConfig dataclass, add this field:

    # --- Stem separation (STORY-008) ---
    stem_config: StemConfig = field(default_factory=StemConfig)

Don't forget to add the import at the top:

    from dataclasses import dataclass, field

═══════════════════════════════════════════════════════════════════════════════
3. ANALYSIS/TYPES.PY — Add StemAction and StemSeparationResult
═══════════════════════════════════════════════════════════════════════════════

File: suno_mastering/analysis/types.py

Add these dataclasses after the existing ones:

    # ── STORY-008: Stem separation types ──────────────────────────────────────

    @dataclass
    class StemAction:
        \"\"\"Records one DSP operation applied to a stem during pre-processing.
        
        Attributes:
            stem_name: "vocals" | "drums" | "bass" | "other"
            action_type: "mono_sub" | "hf_rolloff" | "lf_cut" | "passthrough"
            parameters: dict with filter-specific keys (frequency_hz, filter_type, order)
        \"\"\"
        stem_name: str
        action_type: str  # e.g., "mono_sub", "hf_rolloff", "lf_cut"
        parameters: dict  # e.g., {"frequency_hz": 15000, "filter_type": "low_pass"}


    @dataclass
    class StemSeparationResult:
        \"\"\"Summary of stem separation and processing for reporting.
        
        Populated when --split-stems is invoked. Included in MasteringResult
        and rendered in the Stem Pre-Processing section of output reports.
        
        Attributes:
            model_used: Demucs model name (e.g., "htdemucs")
            separation_time_s: Wall-clock time for AI separation (Phase A)
            actions_applied: List of StemAction records (Phase B)
        \"\"\"
        model_used: str
        separation_time_s: float
        actions_applied: list  # list[StemAction]

═══════════════════════════════════════════════════════════════════════════════
4. PIPELINE.PY — Integrate Stem Preprocessing
═══════════════════════════════════════════════════════════════════════════════

File: suno_mastering/pipeline.py

Step 4a: Update MasteringResult dataclass to include stem_result field:

    @dataclass
    class MasteringResult:
        output_path: str
        before: Measurements
        after: Measurements
        actions: dict
        report: report_builder.ReportData
        input_hash: str
        output_hash: str
        integrity_verified: bool
        below_documented_lufs_floor: bool
        stem_separation: Optional[StemSeparationResult] = None  # STORY-008

    Don't forget to add the import:
        from typing import Optional
        from .analysis.types import StemSeparationResult

Step 4b: In the master() function, add stem preprocessing AFTER ingest and BEFORE
         Stage 2 (measure_all). Find this section:

    # --- Stage 1: Ingest & Validate ---
    logger.info("Stage [1]: Ingest & Validate")
    ingested = ingest_mod.ingest(input_path)
    audio = ingested.audio
    sr = ingested.sample_rate

Add this immediately after:

    # --- STORY-008: Optional Stem Separation Pre-Processing ---
    stem_result = None
    if config.stem_config.enabled:
        logger.info("=" * 70)
        logger.info("STEM SEPARATION PRE-PROCESSING (STORY-008)")
        logger.info("=" * 70)
        from .stem_integration import run_stem_preprocessing
        audio, stem_result = run_stem_preprocessing(
            audio=audio,
            sample_rate=sr,
            stem_config=config.stem_config,
        )
        logger.info("Stem preprocessing complete. Proceeding to Stage [2].")

Step 4c: At the end of master(), when constructing MasteringResult, add:

    return MasteringResult(
        output_path=output_path,
        before=before,
        after=after,
        actions=actions,
        report=report_data,
        input_hash=ingested.input_hash,
        output_hash=export_result.output_hash,
        integrity_verified=integrity_ok,
        below_documented_lufs_floor=solver_outcome.below_soft_band,
        stem_separation=stem_result,  # STORY-008
    )

═══════════════════════════════════════════════════════════════════════════════
5. CLI.PY — Add Command-Line Flags
═══════════════════════════════════════════════════════════════════════════════

File: suno_mastering/cli.py (or wherever argument parsing is done)

Add these arguments to the argparse parser:

    parser.add_argument(
        "--split-stems",
        action="store_true",
        help="Enable AI stem separation pre-processing (requires demucs/torch)",
    )
    
    parser.add_argument(
        "--stem-model",
        type=str,
        default="htdemucs",
        choices=["htdemucs", "htdemucs_ft", "mdx_extra"],
        help="Demucs model to use for stem separation (default: htdemucs)",
    )

Then, when constructing MasteringConfig from args, add:

    from suno_mastering.config import StemConfig
    
    config = MasteringConfig(
        # ... existing fields ...
        stem_config=StemConfig(
            enabled=args.split_stems,
            model_name=args.stem_model,
        ),
    )

═══════════════════════════════════════════════════════════════════════════════
6. REPORT/BUILDER.PY — Add Stem Section to Reports (Optional)
═══════════════════════════════════════════════════════════════════════════════

File: suno_mastering/report/builder.py

If you want to include stem separation details in the output reports:

Step 6a: Update ReportData dataclass:

    @dataclass
    class ReportData:
        # ... existing fields ...
        stem_separation: Optional[StemSeparationResult] = None  # STORY-008

Step 6b: In the function that generates the Markdown report, add a section:

    def _render_stem_section(stem_result: Optional[StemSeparationResult]) -> str:
        if stem_result is None:
            return ""
        
        lines = []
        lines.append("## Stem Pre-Processing\\n")
        lines.append(f"**Model**: {stem_result.model_used}  ")
        lines.append(f"**Separation Time**: {stem_result.separation_time_s:.1f}s\\n")
        lines.append("### Actions Applied\\n")
        
        for action in stem_result.actions_applied:
            if action.action_type == "passthrough":
                lines.append(f"- **{action.stem_name}**: Pass-through (no processing)")
            elif action.action_type == "mono_sub":
                freq = action.parameters.get("frequency_hz", "?")
                lines.append(
                    f"- **{action.stem_name}**: Mono summing below {freq} Hz "
                    f"({action.parameters.get('order', '?')}th-order "
                    f"{action.parameters.get('filter_type', 'lowpass')})"
                )
            elif action.action_type == "hf_rolloff":
                freq = action.parameters.get("frequency_hz", "?")
                lines.append(
                    f"- **{action.stem_name}**: High-frequency rolloff at {freq} Hz "
                    f"({action.parameters.get('order', '?')}nd-order lowpass)"
                )
            elif action.action_type == "lf_cut":
                freq = action.parameters.get("frequency_hz", "?")
                lines.append(
                    f"- **{action.stem_name}**: Low-frequency cut at {freq} Hz "
                    f"({action.parameters.get('order', '?')}rd-order highpass)"
                )
        
        return "\\n".join(lines)

    Then call this function in the main report builder:
    
        stem_section = _render_stem_section(report_data.stem_separation)
        # Insert stem_section after the header and before "Before Mastering"

Step 6c: For JSON reports, ensure stem_separation is included in the output dict.

═══════════════════════════════════════════════════════════════════════════════
TESTING CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

After making the above changes:

[ ] Run unit tests: pytest tests/test_story008_stem_separation.py -v
[ ] Test dependency error (without demucs): python -m suno_mastering input.wav --split-stems
    → Should raise DependencyError with install instructions
[ ] Test with demucs installed: python -m suno_mastering input.wav --split-stems
    → Should complete successfully, report shows stem section
[ ] Test integration: Verify output audio passes Stage 2 (measure_all) without errors
[ ] Test null sum: Run test_tc802_null_sum_test() (requires demucs)
[ ] Test mono verification: Run test_tc803_bass_mono_verification()

═══════════════════════════════════════════════════════════════════════════════
"""
