# Real-image dataset candidates (checked 2026-10-18)

None of the verified candidates below establishes heavy-burr recall on ForgeSight's provisional plate. No images have been downloaded. Verify license terms against the actual download package before use, especially if the prototype becomes commercial. Checked again on 2026-10-18.

## Target heavy-burr training and held-out evaluation

**No verified candidate.** The team needs an approved component, a physical acceptance guide, representative real captures, reviewed heavy-burr locations, and part/session provenance. A visible milling burr is relevant but does not automatically have the team's heavy-burr severity label.

## Closest burr-related source: needs review and relabeling

The [University of León / SCAYLE milling-workpiece dataset](https://open.scayle.es/en/dataset/classification-of-burrs-in-milling-workpieces-images) publishes JPG images, workpiece masks, and CSV class labels. Its official catalog says **Creative Commons Attribution Share-Alike** but does not specify a version on that page; confirm the exact license terms in the download package before use or redistribution. The [authors' companion repository](https://github.com/uleroboticsgroup/optimized_network_detect_burr_breakage) and [CSV](https://github.com/uleroboticsgroup/optimized_network_detect_burr_breakage/blob/main/data/dataset.csv) show section/image identifiers, part identifiers, height-related columns, and numeric classes. The associated paper is *Optimized network for detecting burr-breakage in images of milling workpieces*, DOI 10.1093/jigpal/jzae024. These are **milled workpieces**, not the ForgeSight reference plate. The public information does not verify that a numeric class means ForgeSight's heavy-burr tolerance failure, nor that burr-localizing boxes are supplied. This source may support exploratory burr classification or manual relabeling after provenance and licensing review; it cannot currently support target held-out heavy-burr claims.

## Auxiliary pretraining and method experiments

| Candidate and official source | Publication | Components / defects / annotation | License and ForgeSight limitation |
|---|---|---|---|
| [MPDD, authors' repository](https://github.com/stepanje/MPDD) | Jezek et al., *Deep learning-based defect detection of metal parts: evaluating current methods in complex conditions*, ICUMT 2021, DOI 10.1109/ICUMT54235.2021.9631567 | Metal manufacturing parts; anomaly-free training and normal/anomalous validation images with pixel masks. The source does **not** establish a labeled heavy-burr class. | [Repository license](https://github.com/stepanje/MPDD/blob/main/LICENSE) is CC BY-NC-SA 4.0. Useful for metal-part anomaly experiments, not a direct burr acceptance set. |
| [MVTec AD 2](https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2) | Heckler-Kram et al., *The MVTec AD 2 Dataset: Advanced Scenarios for Unsupervised Anomaly Detection*, IJCV 2026 | Includes sheet-metal and reflective-metal inspection conditions; anomaly masks for the public test subset. Lighting shifts are relevant. Defects are broader than edge burrs. | Official page states CC BY-NC-SA 4.0 and noncommercial restriction. Not a component-matched burr validation set. |
| [MVTec AD](https://www.mvtec.com/research-teaching/datasets/mvtec-ad) | Bergmann et al., *MVTec AD – A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection*, CVPR 2019 | Metal nut and screw among 15 categories; normal training and anomalous test images with pixel masks. | Official page states CC BY-NC-SA 4.0. Screw/nut anomaly categories do not establish plate edge-burr labels. |
| [KolektorSDD2, ViCoS Lab](https://www.vicos.si/resources/kolektorsdd2/) | Božič, Tabernik, Skočaj, *Mixed supervision for surface-defect detection: from weakly to fully supervised learning*, Computers in Industry 2021 | Production-item surface defects including scratches/spots/imperfections; source describes image-level and pixel-level labels. | Official page states CC BY-NC-SA 4.0. Different part and defect distribution; at most a pretraining or method-development candidate. |

## Software-pipeline and geometry testing only

The [Open Stamped Parts Dataset paper](https://arxiv.org/abs/2403.10369) describes real and synthetic stamped-sheet images with hole boxes/masks. Its synthetic defects concern holes; heavy burr labels are not established. The paper points to a download URL, but an authoritative dataset license was not verified here. Use only after checking terms; it may help test hole geometry and annotation tooling, not heavy-burr recall.

The [Pillar Drill Hole Quality Dataset card](https://huggingface.co/datasets/nikhilr2907/Drilling-Dataset) describes aluminium hole photos and coarse normal/abnormal and grid labels. Its listed abnormalities are failed or partial pierces and dents; burr classes are not separated. A license was not verified on the accessible card. It is unsuitable for target heavy-burr training without further rights review and relabeling.

## Unsuitable or legally unclear

The OSPD and pillar-drill rights above are not verified. Tool-wear datasets and generic steel scratch benchmarks do not supply component-matched edge-burr labels. Do not rebrand their metrics as ForgeSight heavy-burr results.

The search did not verify an openly licensed, component-matched, explicitly heavy-burr-labeled plate dataset. The next data milestone should prioritize controlled captures of the selected physical component with approved edge examples, part/session IDs, lighting variation, calibration references, and measured physical dispositions. Generic scratch datasets must not be used to claim heavy-burr recall.
