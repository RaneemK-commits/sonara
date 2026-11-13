FYI / DONE + NEED · speech → device, ui, lead · @RaneemK-commits @Sommer-Lukas

Speech branch: `speech/mfcc-enrollment` (based on main ac496e6). MFCC + DTW recognition, UNKNOWN
rejection, persistent profiles, enrollment service and ALSA/Piper support are implemented.
No device- or UI-owned production files are changed in this branch.

Verification: 54 tests pass on the speech-only branch; 58 pass in a disposable checkout with
owner proposals applied. Earlier UNO Q verification passed 53 tests, real USB-mic capture and
Piper playback. Short synthetic processing: 298 ms mean / 351 ms p95 with 25 templates.
German corpus diagnostic: 40/40 unrelated five-second windows rejected; board mean 1.19 s.
No held-out personalized intent accuracy claim: the corpus lacks repeated phrases/speaker IDs.

NEED device: integrate roles/speech/integration/device.patch (or adapt its exact hooks from
integration/README.md). Controller needs shared audio_lock + enrollment_active, Talk/always-on
pause, optional manual capture, bounded queue and stale-confirm protection; server needs the
enrollment/profile endpoints and threadpool/lock wrapper; entry point must remove backend CLI.
Remove legacy threshold=0.0 and obsolete model paths from sonara.toml. config.py needs no edit.
room_state.enrollment_active is proposed/additive, pending your CONTRACT publication.
The proposal preserves reboot recovery and the off|on|blink Talk/Confirm/Cancel LED model.

NEED ui/lead: review integration/ui.patch and integration/lead-dependencies.patch. The onboarding
UI, dependency cleanup, scoped docs/results and integration tests are supplied for your merge.
Other agent's ~/sonara and port 8000 are untouched; speech validation used /tmp and port 8012.
