# Submission checklist

- [ ] Gnani registration and eligibility confirmed by the participant.
- [ ] Live Prisma and Timbre round trip demonstrated using programme access.
- [ ] Gemini extraction smoke test passed on the free-tier project; actual configured model/provider accurately disclosed.
- [ ] Independent scenarios, human audio, and practitioner feedback collected; limitations stated.
- [ ] Final benchmark frozen and measured; no invented baseline or speech-accuracy claims.
- [ ] Hosted app checked in a fresh browser; demo accounts and quotas verified.
- [ ] 60-second public video recorded from the working app with fictional data identified.
- [ ] Written explanation includes problem, intended users, actual model use, architecture, evidence, and limitations.
- [ ] LinkedIn/X post published by the participant, tagging Gnani with #GnaniAI and #GreatIndianAIInternshipChallenge.
- [ ] Nominated post link(s) and final materials submitted through the programme's current emailed form by the official cutoff.

The repository implements software and supplies a demo script. It does not register you, contact practitioners, post to social networks, or submit the entry. Your Regrag.AI experience should be described with your actual work and contributions.

## Written explanation draft

ShiftProof explores how small manufacturing teams can hand over work through Hindi/Hinglish voice notes while retaining the evidence behind each report. It separates reported packing completion from reviewed quality clearance, highlights contradictory updates, asks a targeted clarification, and records versioned handover acknowledgements. Reviewers explicitly resolve conflicts; later statements cannot silently erase a quality hold.

The implementation integrates Gnani Prisma for transcription and Timbre for spoken clarification, with Gemini candidate extraction and deterministic reconciliation running locally. AWS integration is paused. The current public demonstration must disclose whether it is running scripted extraction or live models. Synthetic engine checks are included; speech performance, independent benchmark results, and real-world impact must be added only after they have actually been measured.

The complete implementation summary and outstanding evidence are in [the re-rating report](re-rating-report.md). Do not publish contract-check percentages as language or voice accuracy.
