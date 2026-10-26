"""RF Explorer: simulator-generated spectra, polarization observations, carrier plans and residuals."""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import streamlit as st

from geodash import rf


@st.cache_data(show_spinner=False, max_entries=8)
def _scene(group: int, label: str):
    return rf.build_scene(group, label)


def _spectrogram(ax, spec_db, freq, time_s, title):
    image = ax.imshow(spec_db, aspect="auto", origin="upper", cmap="viridis",
                      extent=[freq[0], freq[-1], time_s[-1], time_s[0]])
    ax.set_title(title)
    ax.set_xlabel("Frequency offset (MHz)")
    ax.set_ylabel("Time (s)")
    return image


def render() -> None:
    st.title("RF Explorer")
    st.caption("Spectra and residuals from the existing simulator, for development roles only "
               "(train, val-select, val-calib). Test and matched roles are refused before any simulation runs.")

    c1, c2, c3 = st.columns([1, 2, 1])
    role = c1.selectbox("Development role", rf.DEVELOPMENT_ROLES, index=0)
    groups = rf.development_group_ids(role, limit=20)
    group = c2.selectbox("Scenario group", groups, index=0, format_func=lambda g: f"group {g}")
    label = c3.selectbox("Scene label", rf.labels(), index=0)

    if not st.button("Simulate this scene", type="primary"):
        st.info("Click the button to run the simulator for this scene (about 5 to 10 seconds on a 4-core CPU, "
                "cached afterwards). Nothing is simulated until then.")
        return

    try:
        scene = _scene(int(group), label)
    except rf.DevelopmentRoleRefused as error:
        st.error(str(error))
        return
    except Exception as error:  # show the real error; never substitute a plot
        st.error(f"Simulation failed: {type(error).__name__}: {error}")
        return

    st.success(f"Simulated {scene.role} group {scene.group}, label `{scene.label}`. "
               f"Units: spectra in {scene.units['spectrum']}.")

    st.subheader("Polarization observations (spectrogram)")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    for ax, feed, idx in zip(axes, rf.FEEDS, (0, 1)):
        image = _spectrogram(ax, scene.spec_db[idx], scene.freq_mhz, scene.time_s, f"{feed} monitor observation")
    fig.colorbar(image, ax=axes, label="dB(power/Hz), simulator-normalised", shrink=0.9)
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("Mean spectra and carrier plans")
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(12, 6.2), sharex=True)
    top.plot(scene.freq_mhz, scene.mean_psd_db[0], label="co-pol observation", color="tab:blue")
    top.plot(scene.freq_mhz, scene.mean_psd_db[1], label="cross-pol observation", color="tab:orange")
    top.set_ylabel("dB(power/Hz), simulator-normalised")
    top.set_title("Time-averaged monitor spectrum (average taken in linear power)")
    top.legend(loc="upper right")
    bottom.plot(scene.freq_mhz, scene.plan_mask_db[0], label="co-pol plan", color="tab:blue", linestyle="--")
    bottom.plot(scene.freq_mhz, scene.plan_mask_db[1], label="cross-pol plan", color="tab:orange", linestyle="--")
    bottom.set_ylabel("plan mask (dB)")
    bottom.set_xlabel("Frequency offset (MHz)")
    bottom.set_title("Operator carrier plans, dB relative to each plan's own peak (floored at -60 dB)")
    bottom.legend(loc="upper right")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    st.caption("The spectrum scale is simulator-normalised and relative. It is not absolute power in dBm. "
               "Plan masks are shown on their own scale, so they are not overlaid on the spectrum.")

    st.subheader("Observation-based cancellation residual (co-pol, obs-cancel/1)")
    fig, ax = plt.subplots(figsize=(12, 3.8))
    ax.plot(scene.freq_mhz, scene.mean_psd_db[0], label="co-pol observation", color="tab:blue")
    ax.plot(scene.freq_mhz, scene.residual_mean_psd_db, label="residual after removing planned co-pol carriers",
            color="tab:green")
    ax.set_xlabel("Frequency offset (MHz)")
    ax.set_ylabel("dB(power/Hz), simulator-normalised")
    ax.set_title("Residual on the same scale as the observation (time-averaged)")
    ax.legend(loc="upper right")
    st.pyplot(fig)
    plt.close(fig)
    st.caption("The residual is computed from the co-pol monitor IQ and the co-pol operator plan only. "
               "No simulator truth is an input to it.")

    st.subheader("Carrier plans")
    st.dataframe(rf.carriers_frame(scene), hide_index=True, width="stretch")

    with st.expander("Cancellation diagnostics (observation-derived, per planned carrier)"):
        st.json(list(scene.cancellation), expanded=False)
    with st.expander("Simulator truth (metadata; never a model input)"):
        st.write("This block is simulator truth. It is shown for inspection only.")
        st.code(json.dumps(scene.truth, indent=2, allow_nan=False), language="json")
    with st.expander("Units and axes"):
        for key, value in scene.units.items():
            st.write(f"**{key}**: {value}")
        st.write(f"Snapshots: {len(scene.time_s)}; spectral bins: {len(scene.freq_mhz)}; "
                 f"frequency span {scene.freq_mhz[0]:.2f} to {scene.freq_mhz[-1]:.2f} MHz "
                 f"(bin width {(scene.freq_mhz[1] - scene.freq_mhz[0]) * 1000:.4g} kHz).")
