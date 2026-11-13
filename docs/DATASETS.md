# Impaired-speech datasets

Researched 2026-11-13. Never commit dataset audio to this repo: `data/` is git-ignored and most
licenses forbid redistribution.

## Recommendation
Use **both** a dataset and our own recordings, for different purposes:

| Purpose | Source | Why |
|---|---|---|
| **Credible evaluation** of the method on real dysarthric speech | **TORGO** (free, academic) | Real patients (cerebral palsy / ALS), per-speaker folders, includes command-style single words, available immediately |
| **Demo vocabulary** (HELP, WATER, FOOD, PAIN, BATHROOM) | Our own recordings (`scripts/enroll.py --keep-audio`), labelled `--simulated` | TORGO doesn't contain our exact phrases, and the real product enrolls each patient's own voice anyway |

Pitch line: *"On real dysarthric speakers from TORGO, enrolling 3 examples per word gives X% accuracy,
versus Y% for Whisper-tiny. Our live demo uses team-recorded phrases, labelled as simulated."*

TORGO has no HELP/WATER/FOOD-style words. Evaluate on its **command words** (`yes, no, up, down,
left, right, forward, back, select, menu`, digits) per speaker: enroll k takes, test on the rest.
This tests the same few-shot method on real impaired speech.

## Candidates

### TORGO — use this ✅
- Univ. of Toronto. 7 dysarthric speakers (F01, F03, F04, M01–M05; CP or ALS) + 7 controls. 16 kHz.
- Single words include digits, *yes, no, up, down, left, right, forward, back, select, menu*, NATO
  alphabet, plus sentences.
- **License:** free for academic (non-profit) use. Cite one of the Rudzicz et al. 2012 papers. Provided as-is.
- **Download:** `F.tar.bz2` (dysarthric female), `M.tar.bz2` (dysarthric male); controls in `FC`/`MC`.
  ~18 GB uncompressed for all four. We only need F + M. Start the download early.
- Official page: https://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html
- Hugging Face partial copy `abnerh/TORGO-database` (~1.6 GB, parquet, with transcription, severity,
  gender) is faster, **but it has no speaker-ID column**. Few-shot enrollment has to be per speaker,
  so prefer the original archives. Check the HF copy before relying on it.

### UA-Speech — not feasible in 24 h ❌
- Univ. of Illinois. 15 dysarthric (CP) + 13 controls. Isolated words: digits, letters, computer
  commands, common/uncommon words.
- Access by request form (institutional e-mail, IRB-approved data, no redistribution). Approval won't come in time.

### Speech Accessibility Project (SAP) — not feasible in 24 h ❌
- Univ. of Illinois / Beckman. The largest English impaired-speech corpus (Parkinson's, ALS, CP, stroke, Down syndrome).
- Needs a signed data use agreement plus a one-page proposal, reviewed by a committee. Mention it as future work.

### EasyCall — optional, for the "any language" claim ⚠
- Italian dysarthric **voice-command** corpus. 31 dysarthric + 24 healthy speakers, 21k clips,
  includes non-command "distractor" words, which are good for rejection tests.
- Described as public, but we couldn't confirm the download link or dataset license. Check before using.

## Consent and labelling rules
- Team recordings: consent from each teammate. Label them as **acted/simulated** in every result
  (`evaluate.py --simulated`). Don't imitate a specific condition on stage.
- Dataset results: say "TORGO dysarthric speakers", cite the paper, and don't claim clinical validity.
