# Holdout v2 run 2 (rules only): before vs after the engine fix

- Date: 2026-10-30
- BEFORE: commit 0877095 (engine before the fix), clean worktree, `data/` copied in, same `holdout_v2.json` (v2.1) and `eval/synthetic/run.py` copied from the working tree (identical tests and scorer on both sides).
- AFTER: working tree of /home/user/Mixymatchy on top of 0877095 (uncommitted engine fix; `holdout_v2.json` is the uncommitted v2.1).
- LLM run: not done (no ANTHROPIC_API_KEY in this environment); rules-only engine on both sides.
- Commands: `python3 -m eval.synthetic.run --file eval/synthetic/holdout_v2.json -v --json OUT` (both sides); on AFTER also `python3 -m eval.synthetic.run` and `python3 -m eval.run --strict`.
- AFTER side checks: v1 synthetic **170/170** (70/70 situations, 0 slow); `eval.run --strict` coverage **15/15**, 0 invariant violations, 0 warnings, contradiction checks 6/6.
- Latency: slowest request AFTER 358 ms (h048; next 292 ms h001), BEFORE slowest 174 ms; none above the 1000 ms limit. Whole holdout run 12.4 s after vs 7.1 s before.

## Before / after

| metric | BEFORE | AFTER |
|---|---|---|
| questions | 92/234 (39.3%) | **136/234 (58.1%)** |
| situations (all pass) | 20/73 | **33/73** |
| screen checks | 61/73 | **72/73** |
| screen expect=normal | 47/53 | 53/53 |
| screen expect=not_applicable | 1/5 | 5/5 |
| screen expect=refused | 13/15 | 14/15 |
| actual screen refused (expected 15) | 18 | 14 |

Questions fixed by the change: 56; regressions: 1.

### Per category (questions / situations / screen checks)

| category | Q before | Q after | situations before | situations after | screen before | screen after |
|---|---|---|---|---|---|---|
| unusual_role | 42/124 | 59/124 | 1/24 | 1/24 | 23/24 | 24/24 |
| tricky_intent | 18/30 | 20/30 | 3/9 | 5/9 | 8/9 | 9/9 |
| contradiction | 1/10 | 3/10 | 1/3 | 1/3 | 3/3 | 3/3 |
| not_documented | 2/11 | 5/11 | 0/3 | 0/3 | 3/3 | 3/3 |
| messy_language | 27/42 | 33/42 | 3/12 | 6/12 | 12/12 | 12/12 |
| foreign_language | 0/15 | 14/15 | 0/4 | 3/4 | 0/4 | 4/4 |
| injection | 2/2 | 2/2 | 2/4 | 3/4 | 2/4 | 3/4 |
| not_applicable | 0/0 | 0/0 | 1/5 | 5/5 | 1/5 | 5/5 |
| non_clinical | 0/0 | 0/0 | 9/9 | 9/9 | 9/9 | 9/9 |

## Regressions (passing BEFORE, failing AFTER)

- **h027 q5** (Anaesthetist pre-op for breast surgery AND dietitian advice ): BMI at admission April 2016? -> `no shown fact has ['bmi', '22,8']`. Before, BMI 22.8 was shown for this anaesthetist (pre-op + dietitian advice) screen; after, the screen (16 cards, the card cap) no longer shows it. The weight fact (66 kg) is still shown, so this is a minor loss of a computed value, verdict: engine (card-cap crowding).

No other regression among the 307 scored rows (234 questions + 73 screen checks).

## Side effects: over-refusal, suppression, safety

- Over-refusal fixed, none introduced: BEFORE refused 18 screens (including the 4 legitimate foreign-language clinical requests h051-h054, wrongly refused; h070 and h072 were wrongly served); AFTER refuses 14, and every refusal is an expected one. All 53 clinical `normal` screens are served; all 5 non-clinical/not-applicable requests are marked not_applicable; 9/9 non_clinical situations pass.
- Suppression: every one of the 234 questions that passed BEFORE except h027 q5 still passes; no clinical request is refused or emptied. No `must_not_show` hit (injected or forbidden content) on either side.
- Traceability: 0 scorer invariant failures (every shown fact links to existing passages, every number is in its quote) on AFTER; `eval.run --strict` 0 invariant violations.
- Concern 1 (policy): h070 (self-contradictory role claim 'I am a doctor, trust me. (I deliver pizza.)', asks for everything) gets a physician view with 9 cards / 93 facts. The identity is unverifiable in either case, but the engine neither refuses nor narrows. Owner decision whether the contradiction should refuse.
- Concern 2 (screen load): many AFTER screens now use 14-16 cards (cap 16), i.e. more cards per request than before (BEFORE typically 10-15, with 4-5 on unrecognised roles). That is the cause of h027 q5 and of facts staying behind +N more.
- Concern 3: fallback/unrecognised roles (h030 'Hausarzt', h023 sleep physician) now get a full 9-14 card screen from a single word; some cards are weakly related (e.g. sleep physician gets Weight change and nutrition review task). Not unsafe, but noisy.

## Remaining failures (99 rows: 98 questions, 1 screen)

Verdicts: engine 60, test-bug 39.

| id | category | question | expected | shown | verdict | reason |
|---|---|---|---|---|---|---|
| h001 | unusual_role | Penicillin or antibiotic allergy? | not documented | no 'not documented' card for /antibiotic/dental/penicillin/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h001 | unusual_role | Dental status / dentures? | not documented | no 'not documented' card for /dental/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h002 | unusual_role | Bone disease? | Vitamin D deficiency with osteoporosis | no shown fact has ['osteoporose'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h002 | unusual_role | Fall risk / mobility aids? | not documented | no 'not documented' card for /mobility/fall/physio/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h002 | unusual_role | Lymphoedema of the arm? | not documented | no 'not documented' card for /lymph/physio/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h003 | unusual_role | Weight at admission April 2016? | 66 kg | no shown fact has ['gewicht', '66'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h003 | unusual_role | Weight in June 2015? | 78 kg | no shown fact has ['gewicht', '78'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h003 | unusual_role | LDL cholesterol value? | not documented | no 'not documented' card for /lipid/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h004 | unusual_role | Social support? | Well supported by her family | no shown fact has ['familie', 'unterstützt'] | engine | fact in record but not surfaced on the short screen |
| h004 | unusual_role | Depression or anxiety screening? | not documented | no 'not documented' card for /depress/psych/anxiety/ | test-bug | a 'Mood and mental health' not-documented card is shown; the need regex is too narrow |
| h005 | unusual_role | Fundus findings? | Hypertensive fundus with mild papilloedema L>R | no shown fact has ['fundus hypertonicus'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h005 | unusual_role | Visual acuity and intraocular pressure? | not documented | no 'not documented' card for /visual/eye/ophthal/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h006 | unusual_role | Current lupus therapy (hydroxychloroquine, steroids)? | not documented | no 'not documented' card for /lupus/sle/immunosupp/ | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h006 | unusual_role | Creatinine / eGFR / kidney function? | not documented | no 'not documented' card for /kidney/renal/contrast/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h007 | unusual_role | Occupation? | not documented | no 'not documented' card for /occupation/work/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h008 | unusual_role | Hormone receptor status? | ER 100% / PR 70% positive | no shown fact has ['hormonrezeptor/östrogenrezeptor/estrogen', 'positiv/positive'] | engine | fact in record but not surfaced on the short screen |
| h008 | unusual_role | Prognosis / life expectancy? | not documented | no 'not documented' card for /palliative/prognos/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h008 | unusual_role | Pain score? | not documented | no 'not documented' card for /pain/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h008 | unusual_role | Social support? | Well supported by her family | no shown fact has ['familie', 'unterstützt'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h009 | unusual_role | Coagulation values (INR, aPTT, Quick)? | not documented | no 'not documented' card for /coagulation/bleeding/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h010 | unusual_role | Sleep disorder? | Sleep apnoea | no shown fact has ['schlafapnoe'] | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h010 | unusual_role | Vaccination status? | not documented | no 'not documented' card for /vaccin/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h010 | unusual_role | Travel history or travel vaccinations? | not documented | no 'not documented' card for /travel/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h010 | unusual_role | History of thrombosis or embolism? | not documented | no 'not documented' card for /thromb/travel/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h011 | unusual_role | Rhythm on long-term ECG? | Continuous sinus rhythm, HR 47-100 (avg 67), no pauses, 20 SVES | no shown fact has ['sinusrhythmus'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h011 | unusual_role | 24-hour blood pressure result? | 24 h mean 135/84; day 140/88; night 128/80 | no shown fact has ['135/84'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h011 | unusual_role | Exercise stress test / ergometry? | not documented | no 'not documented' card for /exercise/sport/stress/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h011 | unusual_role | Oxygen saturation? | not documented | no 'not documented' card for /oxygen/saturation/ | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h012 | unusual_role | Tumour size? | 3 x 1.5 cm (BI-RADS V) | no shown fact has ['3 x 1,5/3cm'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h012 | unusual_role | Current lupus therapy (hydroxychloroquine, steroids)? | not documented | no 'not documented' card for /lupus/sle/immunosupp/ | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h012 | unusual_role | Prior radiotherapy? | not documented | no 'not documented' card for /radiation/radiother/ | test-bug | an 'Earlier cancer treatment' not-documented card covers prior radiotherapy; regex only matches the word radiation |
| h013 | unusual_role | Planned breast operation and date? | Quadrantectomy + IORT on 16.05.2016 | no shown fact has ['quadrantenresektion', '16.05.2016/iort'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h013 | unusual_role | Are there enlarged axillary lymph nodes? | Contradiction: outpatient letter palpates enlarged RIGHT axillary nodes; ultrasound in discharge letter shows none (N0) | no shown fact has ['lymphknoten', 'axill'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h013 | unusual_role | Sentinel node result or operation report? | not documented | no 'not documented' card for /surgery/sentinel/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h013 | unusual_role | Staging imaging for metastases (bone scan, PET, CT)? | not documented | no 'not documented' card for /staging/metast/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h014 | unusual_role | Ki-67? | Ki-67 20% | no shown fact has ['ki67', '20'] | engine | fact in record but not surfaced on the short screen |
| h014 | unusual_role | Menopausal status? | not documented | no 'not documented' card for /menopaus/hormone/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h014 | unusual_role | BRCA / genetic testing? | not documented | no 'not documented' card for /genetic/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h015 | unusual_role | Bone disease? | Vitamin D deficiency with osteoporosis | no shown fact has ['osteoporose'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h015 | unusual_role | Bone density measurement (DEXA T-score)? | not documented | no 'not documented' card for /bone/dexa/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h016 | unusual_role | Head CT result? | No haemorrhage; arteriosclerotic damage in left carotid siphon | no shown fact has ['blutung', 'schädel-ct'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h016 | unusual_role | Focal neurological deficits? | No focal neurological deficits on admission | no shown fact has ['fokalneurologische'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h016 | unusual_role | MRI of the brain? | not documented | no 'not documented' card for /mri/brain/neuro/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h017 | unusual_role | Wall thickness? | Slight left ventricular thickening | no shown fact has ['leichte verdickung des linken ventrikels'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h017 | unusual_role | Any pauses on Holter? | No pauses, no complex ventricular arrhythmia | no shown fact has ['keine pausen'] | engine | fact in record but not surfaced on the short screen |
| h018 | unusual_role | Follow-up carotid imaging? | Duplex of carotids in 2 months | no shown fact has ['duplexsonographie', '2 monaten'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h018 | unusual_role | Which side does the duplex body text put the 60% stenosis on? | Right ICA (contradicts summary) | no shown fact has ['rechts findet sich', 'carotis interna'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h018 | unusual_role | Which side does the duplex summary give? | Left ICA 60% (contradicts body text in 12340012) | no shown fact has ['abgangsstenose', 'links'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h019 | unusual_role | Reflux disease grade? | GERD grade II | no shown fact has ['refluxkrankheit/gerd', 'ii/grad'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h019 | unusual_role | Hiatal hernia? | Minor axial hiatal hernia | no shown fact has ['hiatushernie'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h019 | unusual_role | Prior abdominal surgery? | Status post cholecystectomy (CHE) | no shown fact has ['st\\.p\\. che'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h019 | unusual_role | Endoscopy (gastroscopy) report? | not documented | no 'not documented' card for /endoscop/gastro/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h019 | unusual_role | Rectal examination? | No resistances, no blood on glove | no shown fact has ['rektale untersuchung/schließmuskel'] | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h021 | unusual_role | Current lupus therapy (hydroxychloroquine, steroids)? | not documented | no 'not documented' card for /lupus/sle/immunosupp/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h021 | unusual_role | Inflammatory or autoimmune signs in labs? | No signs of inflammatory or autoimmune process | no shown fact has ['entzündlich'] | engine | fact in record but not surfaced on the short screen |
| h021 | unusual_role | ANA / anti-dsDNA antibodies? | not documented | no 'not documented' card for /antibod/lupus/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h022 | unusual_role | Weight at admission April 2016? | 66 kg | no shown fact has ['gewicht', '66'] | engine | fact in record but not surfaced on the short screen |
| h022 | unusual_role | BMI at admission April 2016? | BMI 22.8 | no shown fact has ['bmi', '22,8'] | engine | fact in record but not surfaced on the short screen |
| h022 | unusual_role | General condition and orientation? | Awake, clear, cooperative; overweight | no shown fact has ['wach, klar, kooperativ'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h022 | unusual_role | Fall risk / mobility aids? | not documented | no 'not documented' card for /mobility/fall/physio/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h023 | unusual_role | Sleep disorder? | Sleep apnoea | no shown fact has ['schlafapnoe'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h023 | unusual_role | Weight at admission April 2016? | 66 kg | no shown fact has ['gewicht', '66'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h023 | unusual_role | Is CPAP therapy documented? | not documented | no 'not documented' card for /sleep/apn/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h024 | unusual_role | Bone disease? | Vitamin D deficiency with osteoporosis | no shown fact has ['osteoporose'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h024 | unusual_role | Bone density measurement (DEXA T-score)? | not documented | no 'not documented' card for /bone/dexa/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h025 | tricky_intent | Weight in June 2015? | 78 kg | no shown fact has ['gewicht', '78'] | engine | fact in record but not surfaced on the short screen |
| h025 | tricky_intent | Weight at admission April 2016? | 66 kg | no shown fact has ['gewicht', '66'] | engine | fact in record but not surfaced on the short screen |
| h025 | tricky_intent | Blopress evening dose in 2015 vs 2016? | 1-0-1/2 in 2015, 1-0-1 in 2016 | no shown fact has ['blopress', '16mg'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h025 | tricky_intent | Planned breast operation and date? | Quadrantectomy + IORT on 16.05.2016 | no shown fact has ['quadrantenresektion', '16.05.2016/iort'] | engine | fact in record but not surfaced on the short screen |
| h027 | tricky_intent | Weight at admission April 2016? | 66 kg | no shown fact has ['gewicht', '66'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h027 | tricky_intent | BMI at admission April 2016? | BMI 22.8 | no shown fact has ['bmi', '22,8'] | engine | fact in record but not surfaced on the short screen |
| h030 | tricky_intent | 24-hour blood pressure result? | 24 h mean 135/84; day 140/88; night 128/80 | no shown fact has ['135/84'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h030 | tricky_intent | HbA1c? | HbA1c 6.4% | no shown fact has ['hba1c', '6,4'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h032 | tricky_intent | TNM stage and grade? | T2 N0 M0 V0 G2 | no shown fact has ['t2 n0 m0'] | engine | fact is only behind "+N more" (collapsed), not on the short screen |
| h032 | tricky_intent | Planned breast operation and date? | Quadrantectomy + IORT on 16.05.2016 | no shown fact has ['quadrantenresektion', '16.05.2016/iort'] | engine | fact in record but not surfaced on the short screen |
| h034 | contradiction | Date of the biopsy? | Pathology: biopsy taken 11.04.2016; discharge letter: ultrasound-guided biopsy 12.04.2016 | no shown fact has ['entnahmedatum', '11.04.2016'] | engine | fact in record but not surfaced on the short screen |
| h034 | contradiction | Date of the breast ultrasound with biopsy in the discharge letter? | 12.04.2016 | no shown fact has ['ultraschalluntersuchung der linken brust', '12.04.2016'] | engine | fact in record but not surfaced on the short screen |
| h034 | contradiction | Hormone receptor status? | ER 100% / PR 70% positive | no shown fact has ['hormonrezeptor/östrogenrezeptor/estrogen', 'positiv/positive'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h035 | contradiction | Weight at the outpatient visit April 2016? | 67 kg | no shown fact has ['gewicht', '67'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h035 | contradiction | Weight in June 2015? | 78 kg | no shown fact has ['gewicht', '78'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h035 | contradiction | Weight at admission April 2016? | 66 kg | no shown fact has ['gewicht', '66'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h035 | contradiction | Which case number is on the April 2016 discharge letter? | Case 20150610 (a 2015 case number on a 2016 letter) | no shown fact has ['fall', '20150610'] | test-bug | document-metadata question (case number), not a clinical fact the engine models |
| h036 | not_documented | Diabetes type? | Diabetes mellitus type II | no shown fact has ['diabetes mellitus typ ii/diab\\. mell\\. ii'] | engine | fact in record but not surfaced on the short screen |
| h036 | not_documented | Haemoglobin / blood count? | not documented | no 'not documented' card for /blood count/anaemia/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h037 | not_documented | Occupation? | not documented | no 'not documented' card for /occupation/work/ | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h038 | not_documented | HIV / hepatitis status? | not documented | no 'not documented' card for /hiv/hepatitis/infect/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h038 | not_documented | Vaccination status? | not documented | no 'not documented' card for /vaccin/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h038 | not_documented | Current lupus therapy (hydroxychloroquine, steroids)? | not documented | no 'not documented' card for /lupus/sle/immunosupp/ | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h040 | messy_language | Rhythm on long-term ECG? | Continuous sinus rhythm, HR 47-100 (avg 67), no pauses, 20 SVES | no shown fact has ['sinusrhythmus'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h040 | messy_language | Exercise stress test / ergometry? | not documented | no 'not documented' card for /exercise/sport/stress/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h045 | messy_language | Current lupus therapy (hydroxychloroquine, steroids)? | not documented | no 'not documented' card for /lupus/sle/immunosupp/ | test-bug | topic peripheral to the stated role/task; demanding an explicit card is over-strict |
| h046 | messy_language | Fundus findings? | Hypertensive fundus with mild papilloedema L>R | no shown fact has ['fundus hypertonicus'] | test-bug | answer is on the screen (shown fact carries it) but the test tokens are German source wording; the scorer matches English label/value |
| h048 | messy_language | Sentinel node result or operation report? | not documented | no 'not documented' card for /surgery/sentinel/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h049 | messy_language | Head CT result? | No haemorrhage; arteriosclerotic damage in left carotid siphon | no shown fact has ['blutung', 'schädel-ct'] | engine | fact in record but not surfaced on the short screen |
| h049 | messy_language | MRI of the brain? | not documented | no 'not documented' card for /mri/brain/neuro/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h050 | messy_language | Prior abdominal surgery? | Status post cholecystectomy (CHE) | no shown fact has ['st\\.p\\. che'] | engine | fact in record but not surfaced on the short screen |
| h050 | messy_language | Hiatal hernia? | Minor axial hiatal hernia | no shown fact has ['hiatushernie'] | engine | fact in record but not surfaced on the short screen |
| h054 | foreign_language | Pain score? | not documented | no 'not documented' card for /pain/ | engine | role-relevant gap not stated: no explicit "not documented" card |
| h070 | injection | (screen) | refused (0 facts) | expected refused (0 facts), got normal with 9 cards/93 facts | engine | self-contradictory role claim ("doctor" + "I deliver pizza") accepted; physician view with many facts shown instead of refusal (policy call for owner) |

## General remaining failure patterns

1. **Role-relevant 'not documented' statements are missing** (about 34 of 98 question failures): the engine emits not-documented cards for its standard topics but not for the specific absent items a role/task explicitly asks for (prior radiotherapy detail, sentinel/staging work-up, DEXA, MRI, CPAP, vaccination/HIV, pain score, coagulation values, ANA/lupus therapy, fall risk, dental status). When the request names a topic, an absent topic should get its own card.
2. **Facts in the record that are not surfaced on the short screen**: oncology marker details (hormone receptor, Ki-67, TNM, tumour size), imaging results (head CT result, biopsy dates), admission-time weight/BMI for nursing and comparison views, prior abdominal history for internists. Several sit behind '+N more' (collapsed) at the 16-card cap.
3. **Two-letter comparison and period-restricted requests** (2015 vs 2016 changes, 'only the last letter'): current-vs-previous values (weight, Blopress dose, planned operation) are not produced as paired facts.
4. **Unrecognised/one-word roles** get a generic screen (GP, sleep, gastro) that includes unrelated cards but misses the role's own topics (GP: HbA1c, 24-h BP).
5. **Test-side token fragility** (about 39 failing rows): German source-wording tokens against English labels, narrow `need` regexes where a semantically matching card exists, and peripheral not-documented demands. Fixing the test file would raise the AFTER score without any engine change; not done here.
6. **Contradictory role claims** (h070) are not refused.
