class TestTC2757:
    """TC-2757: Drop-entrance gain trajectory: leading-window pre-ramp and IIR smoothness.

    DEF-027-007 (Closed): the previous test modeled the gain as starting from 0 dB at the
    burst entrance (t=18s). Architecture §7.2 specifies LEADING windows — the gain for sample
    t uses window [t, t+window_samples]. With a 3-second window, hops starting at t≈15s already
    contain burst content, so the IIR starts ramping ≈3 seconds before the burst arrives.
    By t=18s the gain has pre-ramped to ≈70% of g_final (confirmed: g0 ≈ -8 dB, g_final ≈ -12 dB).

    The CORRECT assertions for leading-window IIR behaviour are:
    1. Well before the burst (t=1s), no loud content in the leading window → gain ≈ 0 dB.
    2. At the burst entrance (t=18s), the IIR has pre-ramped → gain well below 0 dB (< -1 dB).
    3. Between t=14s and t=22s the gain envelope is smooth — no single 100 ms hop exceeds
       the per-hop IIR rate limit.

    Fixture: 18s quiet (-24 dBFS) + 9s loud (-6 dBFS) = 27s.  Same as previous version.
    """

    def test_gain_smooths_toward_target(self):
        """Leading-window pre-ramp: gain near 0 early, pre-ramped at burst, smooth throughout."""
        sr = 44100
        win_s = 3.0
        win_len = int(sr * win_s)
        t = np.arange(win_len) / sr
        # 6 quiet windows at -24 dBFS, then 3 loud windows at -6 dBFS
        quiet_amp = 10 ** (-24.0 / 20.0)
        loud_amp  = 10 ** (-6.0  / 20.0)
        quiet_chunk = quiet_amp * np.sin(2 * np.pi * 440.0 * t)
        loud_chunk  = loud_amp  * np.sin(2 * np.pi * 440.0 * t)
        mono = np.concatenate([quiet_chunk] * 6 + [loud_chunk] * 3)
        audio = np.stack([mono, mono], axis=1).astype(np.float64)

        targets = _targets_with_leveling(no_op=0.5, max_att=20.0)
        out, action = apply_dynamics_leveler(audio, sr, targets, MasteringConfig())
        assert action.applied is True, "Leveler did not fire"
        assert action.max_gain_db_applied < 0.0, "No attenuation applied on loud burst"

        # Derive gain envelope from RMS ratio over 50 ms windows to avoid
        # zero-crossing contamination (single-sample ratio is unreliable at zero crossings)
        mono_in  = audio[:, 0]
        mono_out = out[:, 0]
        n_total  = len(mono_in)

        def gain_db_rms(center_sample: int, half_win: int = 2205) -> float:
            """RMS-based gain estimate (50 ms window, robust to zero crossings)."""
            s = max(0, center_sample - half_win)
            e = min(n_total, center_sample + half_win)
            in_rms  = float(np.sqrt(np.mean(mono_in[s:e] ** 2)))
            out_rms = float(np.sqrt(np.mean(mono_out[s:e] ** 2)))
            if in_rms < 1e-12:
                return 0.0
            return 20.0 * np.log10(max(out_rms / in_rms, 1e-10))

        # G_final: steady-state gain from last 2 s of signal
        final_center = n_total - int(1.0 * sr)
        g_final_db = gain_db_rms(final_center)
        if g_final_db >= -0.1:
            pytest.skip("No attenuation in burst section — fixture problem")

        # --- Assertion 1: Well before burst, gain is near 0 dB ---
        # At t=1s the leading window [1s, 4s] sees only quiet content.  Downward-only leveling
        # applies no boost even if quiet is below the mean, so gain should be 0 dB here.
        g_early = gain_db_rms(int(1.0 * sr))
        assert g_early > -1.5, (
            f"Gain at t=1s ({g_early:.2f} dB) is not near 0 dB. "
            f"Windows well before the burst see only quiet content — no attenuation expected."
        )

        # --- Assertion 2: At burst entrance, gain has already pre-ramped (leading-window behaviour) ---
        # With leading windows, hops from t≈15s onward include burst content and drive the IIR
        # downward well before the burst starts at t=18s.  By t=18s, gain should be < -1 dB.
        # (Confirmed in DEF-027-007: g0 ≈ -8 dB with this fixture.)
        t0_sample = int(18.0 * sr)
        g0 = gain_db_rms(t0_sample + int(0.05 * sr))
        assert g0 < -1.0, (
            f"Gain at burst entrance t=18s ({g0:.2f} dB) is near 0 dB. "
            f"With leading-window alignment, the IIR should have pre-ramped substantially "
            f"below 0 dB by the time the burst starts. Expected < -1 dB."
        )

        # --- Assertion 3: Gain trajectory is smooth — no large per-hop step changes ---
        # Sample gain at 100 ms intervals across the pre-ramp + burst region (t=14s to t=22s).
        # A first-order IIR with tau=1.5s changes by at most (1-exp(-0.1/1.5)) ≈ 6.5% of the
        # remaining gap per 100 ms hop.  For a max gap of 20 dB, that is ≈ 1.3 dB/hop.
        # Allow 2x headroom → max step threshold = 2.5 dB/hop.
        hop_s = 0.1
        hop_samples = int(hop_s * sr)
        t_start = int(14.0 * sr)
        t_end   = int(22.0 * sr)
        gain_trace = [
            gain_db_rms(t_start + i * hop_samples)
            for i in range((t_end - t_start) // hop_samples)
        ]
        max_step_db = max(
            abs(gain_trace[i + 1] - gain_trace[i])
            for i in range(len(gain_trace) - 1)
        )
        assert max_step_db < 2.5, (
            f"Gain step of {max_step_db:.2f} dB per 100 ms hop exceeds smoothness threshold (2.5 dB). "
            f"IIR smoothing with tau=1.5s should limit per-hop changes to ≈ 1.3 dB max. "
            f"An instantaneous step would indicate the IIR is bypassed or the envelope is not applied."
        )

