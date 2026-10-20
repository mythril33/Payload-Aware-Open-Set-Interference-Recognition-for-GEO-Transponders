# Original-source register and provenance

Date checked: 2026-10-20. “Original document” means **a primary publisher/author page or original issued file URL**; a Markdown review is **our interpretation**. An external download link is not the same as a byte-for-byte copy inside this repository.

## User-supplied primary brief

- Filename as received: `Payload-Aware Open-Set Interference Recognition for GEO Transponders.docx`
- SHA-256 of byte-for-byte uploaded document: `de550d2b7556d533746c44d6026880625b28c41272f62ec097769161d6891a53`
- Size: 63,348 bytes.
- Faithful *text/table* transcription: [original_proposal.md](original_proposal.md). The two-page DOCX also contains an embedded roadmap image; the Markdown transcription is not binary-identical and the graphic is summarized.
- **Binary status:** this repository's research update does **not** contain the unchanged `.docx` unless a separate commit is visible under `sources/original/`. Keep the source document outside the public GitHub repository until its embedded metadata is reviewed.

## Official primary originals — link to author/publisher, do not mirror automatically

| Primary original | Official URL | Distribution note |
|---|---|---|
| ETSI EN 302 307-1 V1.4.1 original PDF | https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf | Public standards file; copying to GitHub may require permission |
| ETSI TR 102 376-2 V1.2.1 original PDF | https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf | Avoid redistribution; see standards conditions |
| ETSI Annex E source ZIP | https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p0.zip | Reproducibility: download separately, document version and SHA-256 |
| Saleh 1981 original paper (DOI) | https://doi.org/10.1109/TCOM.1981.1094911 | IEEE publisher rights; do not copy without permission |
| Henarejos et al. 2019 author preprint | https://arxiv.org/abs/1906.03012 | arXiv author page; license specific to version |
| Satellite on-board interference SnT dataset | https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/ | SmartSpace: research-only/noncommercial |
| NGSO-to-GSO SnT dataset | https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/ | SmartSpace: research-only/noncommercial |
| Saifaldawla et al. 2024 paper (author preprint, publisher CC BY) | https://orbilu.uni.lu/bitstream/10993/61484/1/TMLCN_Final.pdf | This 2024 paper itself states CC BY 4.0; dataset rights are separate |
| OpenDPD source and measured datasets | https://github.com/lab-emi/OpenDPD ; https://lab-emi.github.io/OpenDPD/datasets/ | Inspect each dataset's license prior to reuse |
| RF WebLab online measurement | https://dpdcompetition.com/rfweblab/access-details/ | GaN PA apparatus, active service; not a downloaded benchmark |
| TorchSig source | https://github.com/TorchDSP/torchsig | Code MIT, generated/measured data terms separate |
| Fraunhofer Spectrum Highway 2 original release | https://doi.org/10.5281/zenodo.21336653 | GNSS data CC BY-NC-SA 4.0, 15.4 GB file |
| Lee et al. Mahalanobis, NeurIPS 2018 | https://proceedings.neurips.cc/paper_files/paper/2018/hash/abdeb6f575ac5c6676b747bca8d09cc2-Abstract.html | Official proceedings |
| Liu et al. energy score, NeurIPS 2020 | https://papers.neurips.cc/paper_files/paper/2020/hash/f5496252609c43eb8a3d147ab9b9c006-Abstract.html | Official proceedings |
| ITU spacecraft spectrum-monitoring source | https://www.itu.int/dms_pub/itu-r/opb/hdb/R-HDB-53-2008-OAS-PDF-E.pdf | ITU publication, redistribution conditions require checking |

## Byte-for-byte original collection procedure

1. Download primary documents from **the links above**, respecting licenses and file size.
2. Keep files under locally ignored `data/external/originals/`, not in this Git history.
3. Record `sha256sum <filename>` (or PowerShell `Get-FileHash`), official URL, retrieval timestamp, version and source license; **never invent checksums for files not downloaded**.
4. For research comparisons, cite original paper/data record and use the derived notes in [P1](../docs/plan/P1_literatur.md) and [P8](../docs/plan/P8_dis_veri.md). 
5. Contact publisher or rightsholder for any planned redistribution. This repository does not automatically grant rights to third-party material.

No third-party PDFs or large RF raw data were fetched, executed or rehosted as part of the research-only Markdown publication.
