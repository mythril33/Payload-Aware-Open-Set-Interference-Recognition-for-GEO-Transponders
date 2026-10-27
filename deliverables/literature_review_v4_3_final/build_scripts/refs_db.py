"""Reference database for V4.3: stable IDs, final IEEE-style citation, verification state, notes.

States: verified_full_text | verified_publisher_metadata | verified_primary_dataset_record |
        secondary_only | unverified | contradicted
"""
import csv, glob, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.dirname(HERE)
REPO = "/home/user/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders"

# Final citation text overrides for legacy references (corrections found in this audit).
CIT = {
 "R001": 'J. Bates, "Satellite operators target interference problem," *Via Satellite*, Aug. 2005. [Online]. Available: https://www.satellitetoday.com/connectivity/2005/08/01/satellite-operators-target-interference-problem/',
 "R002": 'M. Coleman, "Tackling satellite interference," *Microwave Journal*, 2012. [Online]. Available: https://www.microwavejournal.com/articles/18088-tackling-satellite-interference',
 "R003": 'Kratos, "Complete VSAT interference mitigation," product fact sheet, n.d. [Online]. Available: https://www.kratosspace.com/-/media/communications/pdf/fact-sheet---complete-vsat-interference-mitigation.pdf (carrier-under-carrier and PCMA-cancellation capabilities are stated in other Kratos Monics/SatGuard product documents).',
 "R004": 'M. Á. Vázquez, P. Henarejos, A. I. Pérez-Neira, E. Grechi, A. Voight, J. C. Gil, I. Pappalardo, F. Di Credico, and R. M. Lancellotti, "On the use of AI for satellite communications," *IEEE ComSoc SSC Newsletter*, 2019, arXiv:2007.10110.',
 "R005": 'Kratos, "Kratos KnownSpace detects sustained Iran origin RF interference targeting GEO communications," company report, 2026. [Online]. Available: https://www.kratosspace.com/sdatracker/kratos-knownspace-detects-sustained-iran-origin-rf-interference-targeting-geo-communications',
 "R006": 'M. Á. Vázquez, P. Henarejos, I. Pappalardo, E. Grechi, J. Fort, J. C. Gil, and R. M. Lancellotti, "Machine learning for satellite communications operations," *IEEE Commun. Mag.*, vol. 59, no. 2, pp. 22–27, 2021, doi: 10.1109/MCOM.001.2000367.',
 "R007": 'A. I. Pérez-Neira, M. Á. Vázquez, S. Maleki, M. R. B. Shankar, and S. Chatzinotas, "Signal processing for high-throughput satellites: Challenges in new interference-limited scenarios," *IEEE Signal Process. Mag.*, vol. 36, no. 4, pp. 112–131, 2019, doi: 10.1109/MSP.2019.2894391 (preprint arXiv:1802.03958).',
 "R008": 'C. Politis, S. Maleki, C. Tsinos, S. Chatzinotas, and B. Ottersten, "On-board the satellite interference detection with imperfect signal cancellation," in *Proc. IEEE SPAWC*, 2016, pp. 1–5, doi: 10.1109/SPAWC.2016.7536813.',
 "R009": 'C. Politis, S. Maleki, C. Tsinos, S. Chatzinotas, and B. Ottersten, "Weak interference detection with signal cancellation in satellite communications," in *Proc. IEEE ICASSP*, 2017, pp. 6289–6293, doi: 10.1109/ICASSP.2017.7953366.',
 "R010": 'H. M. Finn and R. S. Johnson, "Adaptive detection mode with threshold control as a function of spatially sampled clutter-level estimates," *RCA Review*, vol. 29, no. 3, pp. 414–464, Sep. 1968.',
 "R011": 'W. A. Gardner, "Exploitation of spectral redundancy in cyclostationary signals," *IEEE Signal Process. Mag.*, vol. 8, no. 2, pp. 14–36, Apr. 1991, doi: 10.1109/79.81007.',
 "R012": 'B. Kim, H. Yu, and S. Noh, "Cognitive interference cancellation with digital channelizer for satellite communication," *Sensors*, vol. 20, no. 2, art. 355, 2020, doi: 10.3390/s20020355.',
 "R013": 'ITU-R, "Carrier identification system for FSS occasional use earth station transmissions," Recommendation ITU-R S.2062-0, Sep. 2014.',
 "R014": 'B. Potter, "Preventing adjacent satellite interference," *Via Satellite*, Mar. 2014. [Online]. Available: https://www.satellitetoday.com/technology/2014/03/26/preventing-adjacent-satellite-interference/ (vendor-authored trade article).',
 "R015": 'Rohde & Schwarz, "R&S GSACSM communications system monitoring," product page, n.d. [Online]. Available: https://www.rohde-schwarz.com/us/products/aerospace-defense-security/secure-communications-options/rs-gsacsm-communications-system-monitoring_63493-636288.html',
 "R016": 'Integrasys, "VectorSat interference detection," product information, n.d. [Online]. Available: https://www.integrasys-space.com/interference-detection',
 "R017": 'Calian, "Decimator carrier-under-carrier detection," product page, n.d. [Online]. Available: https://www.calian.com/advanced-technologies/space-satcom/decimator-carrier-under-carrier-detection/',
 "R018": 'P. Henarejos, M. Á. Vázquez, and A. I. Pérez-Neira, "Deep learning for experimental hybrid terrestrial and satellite interference management," in *Proc. IEEE SPAWC*, 2019, pp. 1–5, doi: 10.1109/SPAWC.2019.8815532, arXiv:1906.03012.',
 "R019": 'L. Pellaco, N. Singh, and J. Jaldén, "Spectrum prediction and interference detection for satellite communications," in *Proc. 37th Int. Commun. Satellite Syst. Conf. (ICSSC)*, 2019, arXiv:1912.04716.',
 "R020": 'S. Daoud, G. Eappen, F. Ortiz, E. Lagunas, W. Martins, and S. Chatzinotas, "CNN-based on-board interference detection in satellite systems: An analysis of dataset impact on performance," in *Proc. IEEE ICASSP Workshops (ICASSPW)*, 2023, pp. 1–5, doi: 10.1109/ICASSPW59220.2023.10193395.',
 "R021": 'A. Saifaldawla, F. Ortiz-Gomez, E. Lagunas, S. Daoud, and S. Chatzinotas, "NGSO-to-GSO satellite interference detection based on autoencoder," in *Proc. IEEE PIMRC*, 2023, pp. 1–7, doi: 10.1109/PIMRC56721.2023.10293839.',
 "R022": 'A. Saifaldawla, F. Ortiz, E. Lagunas, and S. Chatzinotas, "Convolutional autoencoders for non-geostationary satellite interference detection," in *Proc. IEEE ICC Workshops*, 2024, pp. 1334–1339, doi: 10.1109/ICCWorkshops59551.2024.10615457.',
 "R023": 'A. Saifaldawla, F. Ortiz, E. Lagunas, A. B. M. Adam, and S. Chatzinotas, "GenAI-based models for NGSO satellites interference detection," *IEEE Trans. Mach. Learn. Commun. Netw.*, vol. 2, pp. 904–924, 2024, doi: 10.1109/TMLCN.2024.3418933.',
 "R024": 'B. Yang, C. Yang, Z. Chen, K. Qiu, and Y. Gao, "Agon: A semi-supervised framework for robust satellite interference detection," arXiv:2606.14147, 2026 (preprint).',
 "R025": 'H. Yu, R. Zhang, and R. Ding, "Interference recognition based on machine learning for satellite communications," in *Proc. Int. Conf. Machine Learning Technologies (ICMLT)*, 2018, pp. 18–23, doi: 10.1145/3231884.3231901.',
 "R026": 'X. Han, "Artificial intelligence-based interference signal recognition for satellite communications," in *Proc. ACSAT*, 2024, pp. 279–282, doi: 10.1109/ACSAT63853.2024.10823708.',
 "R027": 'H. Xiong, "Research on interference detection and identification algorithms for satellite communication systems," in *Proc. ICECAI*, 2025, pp. 84–87, doi: 10.1109/ICECAI66283.2025.11170987.',
 "R028": 'F. Ortiz, V. Monzon Baeza, L. M. Garces-Socarras, J. A. Vásquez-Peralvo, J. L. Gonzalez *et al.*, "Onboard processing in satellite communications using AI accelerators," *Aerospace*, vol. 10, no. 2, art. 101, 2023, doi: 10.3390/aerospace10020101.',
 "R029": 'F. Fourati and M.-S. Alouini, "Artificial intelligence for satellite communication: A review," *Intelligent and Converged Networks*, vol. 2, no. 3, pp. 213–243, 2021, doi: 10.23919/ICN.2021.0015.',
 "R030": 'G. Fontanesi, F. Ortiz, E. Lagunas *et al.*, "Artificial intelligence for satellite communication: A survey," *IEEE Commun. Surveys Tuts.*, 2025, doi: 10.1109/COMST.2025.3534617.',
 "R031": 'A. Bhattacharyya *et al.*, "Machine learning and deep learning powered satellite communications," *Int. J. Satell. Commun. Netw.*, vol. 41, no. 6, pp. 539–588, 2023, doi: 10.1002/sat.1482.',
 "R032": 'T. Brieger, N. L. Raichur, D. Jdidi, F. Ott, T. Feigl, J. R. van der Merwe *et al.*, "Multimodal learning for reliable interference classification in GNSS signals," in *Proc. ION GNSS+*, 2022, pp. 3210–3234, doi: 10.33012/2022.18586.',
 "R033": 'J. R. van der Merwe *et al.*, "Low-cost COTS GNSS interference monitoring, detection, and classification system," *Sensors*, vol. 23, no. 7, art. 3452, 2023, doi: 10.3390/s23073452.',
 "R034": 'F. Ott, L. Heublein, N. L. Raichur, T. Feigl, J. Hansen, A. Rügamer, and C. Mutschler, "Few-shot learning with uncertainty-based quadruplet selection for interference classification in GNSS data," in *Proc. ICL-GNSS*, 2024, doi: 10.1109/ICL-GNSS60721.2024.10578525.',
 "R035": 'L. Heublein, N. L. Raichur, T. Feigl, T. Brieger, F. Heuer *et al.*, "Evaluation of (un-)supervised machine learning methods for GNSS interference classification with real-world data discrepancies," in *Proc. ION GNSS+*, 2024, pp. 1260–1293 (preprint arXiv:2503.23775).',
 "R036": 'L. Heublein *et al.*, "VAE-based feature disentanglement for data augmentation and compression in generalized GNSS interference classification," in *Proc. ICL-GNSS*, 2025, doi: 10.1109/ICL-GNSS65520.2025.11046129 (preprint arXiv:2504.10556).',
 "R037": 'C. Wielenberg, L. Heublein, J. Ott *et al.*, "The S-ICDF dataset: Sionna-simulated dynamic interference characterization and direction finding," arXiv:2607.03411, 2026 (preprint).',
 "R038": 'I. Ebrahimi Mehr and F. Dovis, "A deep neural network approach for classification of GNSS interference and jammer," *IEEE Trans. Aerosp. Electron. Syst.*, vol. 61, no. 2, 2025, doi: 10.1109/TAES.2024.3462662.',
 "R039": 'T. J. O\'Shea, T. Roy, and T. C. Clancy, "Over-the-air deep learning based radio signal classification," *IEEE J. Sel. Topics Signal Process.*, vol. 12, no. 1, pp. 168–179, 2018, doi: 10.1109/JSTSP.2018.2797022.',
 "R040": 'L. Boegner, M. Gulati, G. Vanhoy, P. Vallance, B. Comar, S. Kokalj-Filipovic, C. Lennon, and R. D. Miller, "Large scale radio frequency signal classification," in *Proc. GNU Radio Conf.*, 2022, arXiv:2207.09918.',
 "R041": 'L. Boegner *et al.*, "Large scale radio frequency wideband signal detection & recognition," arXiv:2211.10335, 2022.',
 "R042": 'M. Kulin, T. Kazaz, I. Moerman, and E. De Poorter, "End-to-end learning from spectrum data: A deep learning approach for wireless signal identification in spectrum monitoring applications," *IEEE Access*, vol. 6, pp. 18484–18501, 2018, doi: 10.1109/ACCESS.2018.2818794.',
 "R043": 'K. Tekbıyık, Ö. Akbunar, A. R. Ekti, A. Görçin, G. K. Kurt, and K. A. Qaraqe, "Spectrum sensing and signal identification with deep learning based on spectral correlation function," *IEEE Trans. Veh. Technol.*, vol. 70, no. 10, pp. 10514–10527, 2021, doi: 10.1109/TVT.2021.3109236.',
 "R045": 'T. Oyedare, V. K. Shah, D. J. Jakubisin, and J. H. Reed, "Keep it simple: CNN model complexity studies for interference classification tasks," in *Proc. IEEE INFOCOM Workshops*, 2023, pp. 1–6, arXiv:2303.03326.',
 "R046": 'C. Xu, J. Ren, W. Yu, Y. Jin, Z. Cao, X. Wu, and W. Jiang, "Time-frequency analysis based deep interference classification for frequency hopping system," arXiv:2108.10056v2, 2022 (title and authors of v2; v1 differs).',
 "R047": 'T. Oyedare, V. K. Shah, D. J. Jakubisin, and J. H. Reed, "Interference suppression using deep learning: Current approaches and open challenges," *IEEE Access*, vol. 10, pp. 66238–66266, 2022, doi: 10.1109/ACCESS.2022.3185124.',
 "R048": 'K. He, X. Zhang, S. Ren, and J. Sun, "Deep residual learning for image recognition," in *Proc. IEEE CVPR*, 2016, arXiv:1512.03385.',
 "R049": 'Y. Gong, Y.-A. Chung, and J. Glass, "AST: Audio spectrogram transformer," in *Proc. Interspeech*, 2021, arXiv:2104.01778.',
 "R050": 'E. Perez, F. Strub, H. de Vries, V. Dumoulin, and A. Courville, "FiLM: Visual reasoning with a general conditioning layer," in *Proc. AAAI*, 2018, arXiv:1709.07871.',
 "R051": 'A. A. M. Saleh, "Frequency-independent and frequency-dependent nonlinear models of TWT amplifiers," *IEEE Trans. Commun.*, vol. 29, no. 11, pp. 1715–1720, Nov. 1981, doi: 10.1109/TCOM.1981.1094911.',
 "R052": 'A. Morello and V. Mignone, "DVB-S2: The second generation standard for satellite broad-band services," *Proc. IEEE*, vol. 94, no. 1, pp. 210–227, 2006, doi: 10.1109/JPROC.2005.861013.',
 "R053": 'E. Casini, R. De Gaudenzi, and A. Ginesi, "DVB-S2 modem algorithms design and performance over typical satellite channels," *Int. J. Satell. Commun. Netw.*, vol. 22, no. 3, pp. 281–318, 2004, doi: 10.1002/sat.791.',
 "R054": 'ETSI, "Digital Video Broadcasting (DVB); Implementation guidelines for the second generation system for Broadcasting, Interactive Services, News Gathering and other broadband satellite applications; Part 2: S2 Extensions (DVB-S2X)," ETSI TR 102 376-2 V1.2.1, Jan. 2021 (the 2020 DVB document A171-2 is a preceding draft).',
 "R055": 'B. F. Beidas, "Intermodulation distortion in multicarrier satellite systems: Analysis and turbo Volterra equalization," *IEEE Trans. Commun.*, vol. 59, no. 6, pp. 1580–1590, 2011, doi: 10.1109/TCOMM.2011.042111.100320.',
 "R056": 'M. Allegue-Martínez *et al.*, "Digital linear pre-compensation technique to enhance predistortion performance in multicarrier DVB-S2 satellite communication systems," *Electron. Lett.*, vol. 50, no. 13, pp. 957–959, 2014, doi: 10.1049/el.2014.1172.',
 "R057": 'A. A. Gözütok, M. M. Nefes, and S. Demirel, "NPR and intermodulation distortion modelling of travelling-wave tube amplifier of telecommunication spacecraft," in *Proc. Ankara Int. Aerospace Conf.*, AIAC-2021-015, 2021.',
 "R058": 'J. C. Fuenzalida, O. Shimbo, and W. L. Cook, "Time-domain analysis of intermodulation effects caused by nonlinear amplifiers," *COMSAT Tech. Rev.*, vol. 3, no. 1, pp. 89–143, 1973.',
 "R059": 'Y. Luo, A. Jayaprakash, G. Chen, C. Huang, Q. Luo, and P. Xiao, "Widely linear augmented extreme learning machine based impairments compensation for satellite communications," *IEEE Trans. Veh. Technol.*, 2025, doi: 10.1109/TVT.2025.3581439 (preprint arXiv:2506.14557).',
 "R060": 'X. Sun *et al.*, "Kernel-FastICA-based nonlinear blind source separation for anti-jamming satellite communications," *Sensors*, vol. 25, no. 12, art. 3743, 2025, doi: 10.3390/s25123743.',
 "R061": 'Y. Wu, G. D. Singh, M. Beikmirza, L. C. N. de Vreede, M. Alavi, and C. Gao, "OpenDPD: An open-source end-to-end learning & benchmarking framework for wideband power amplifier modeling and digital pre-distortion," in *Proc. IEEE ISCAS*, 2024, doi: 10.1109/ISCAS58744.2024.10558162.',
 "R062": 'Y. Wu, A. Li, and C. Gao, "OpenDPDv2: A unified learning and optimization framework for neural network digital predistortion," arXiv:2507.06849, 2025.',
 "R063": 'S. Hanna and D. Čabrić, "Deep learning based transmitter identification using power amplifier nonlinearity," arXiv:1811.04521, 2018 (conference version: IEEE ICNC 2019).',
 "R064": 'A. S. Karasuwa, J. D. Eastment, and I. E. Otung, "Cross-polarisation discrimination-induced interference in dual-polarised high-capacity satellite communication systems," *J. Eng.*, vol. 2016, no. 6, pp. 162–170, 2016, doi: 10.1049/joe.2015.0178.',
 "R065": 'E. Satorius, T. Jedrey, and C. Wang, "Impact of cross-polarization interference on dual polarization communication systems," *IPN Progress Report* 42-213, Jet Propulsion Laboratory, May 2018.',
 "R066": 'P. Mo, X. Fan, and L. You, "A novel and blind detection scheme for asymmetric PCMA system," in *Proc. ICCSNT*, 2013, pp. 854–857, doi: 10.1109/ICCSNT.2013.6967240.',
 "R067": 'X. Liu, X. Tao, X. Chen, and N. Ge, "Information theory analysis of blind detection for PCMA satellite communication systems," in *Proc. IEEE VTC-Fall*, 2013, pp. 1–5, doi: 10.1109/VTCFall.2013.6692242.',
 "R068": 'C. Geng, S.-J. Huang, and S. Chen, "Recent advances in open set recognition: A survey," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 43, no. 10, pp. 3614–3631, 2021, doi: 10.1109/TPAMI.2020.2981604.',
 "R069": 'J. Yang, K. Zhou, Y. Li, and Z. Liu, "Generalized out-of-distribution detection: A survey," *Int. J. Comput. Vis.*, vol. 132, no. 12, pp. 5635–5662, 2024, doi: 10.1007/s11263-024-02117-4.',
 "R070": 'D. Hendrycks and K. Gimpel, "A baseline for detecting misclassified and out-of-distribution examples in neural networks," in *Proc. ICLR*, 2017, arXiv:1610.02136.',
 "R071": 'S. Liang, Y. Li, and R. Srikant, "Enhancing the reliability of out-of-distribution image detection in neural networks," in *Proc. ICLR*, 2018, arXiv:1706.02690.',
 "R072": 'W. Liu, X. Wang, J. D. Owens, and Y. Li, "Energy-based out-of-distribution detection," in *Proc. NeurIPS*, 2020, arXiv:2010.03759.',
 "R073": 'K. Lee, K. Lee, H. Lee, and J. Shin, "A simple unified framework for detecting out-of-distribution samples and adversarial attacks," in *Proc. NeurIPS*, 2018, arXiv:1807.03888.',
 "R074": 'A. Bendale and T. E. Boult, "Towards open set deep networks," in *Proc. IEEE CVPR*, 2016, pp. 1563–1572, doi: 10.1109/CVPR.2016.173.',
 "R075": 'G. Chen, P. Peng, X. Wang, and Y. Tian, "Adversarial reciprocal points learning for open set recognition," *IEEE Trans. Pattern Anal. Mach. Intell.*, 2021, doi: 10.1109/TPAMI.2021.3106743.',
 "R076": 'S. Vaze, K. Han, A. Vedaldi, and A. Zisserman, "Open-set recognition: A good closed-set classifier is all you need?," in *Proc. ICLR*, 2022, arXiv:2110.06207.',
 "R077": 'A. R. Dhamija, M. Günther, and T. E. Boult, "Reducing network agnostophobia," in *Proc. NeurIPS*, 2018, arXiv:1811.04110.',
 "R078": 'Y. Guo, H. Jiang, J. Wu, and J. Zhou, "Open set modulation recognition based on dual-channel LSTM model," arXiv:2002.12037, 2020.',
 "R079": 'Z. Zhang, M. Zhu, J. Liu, Y. Li, and S. Wang, "Class information guided reconstruction for automatic modulation open-set recognition," arXiv:2312.13023, 2023.',
 "R080": 'H. Zhang, F. Zhou, Q. Wu, and C. Yuen, "FSOS-AMC: Few-shot open-set learning for automatic modulation classification," arXiv:2410.10265, 2024.',
 "R081": 'Y. Yang, S. Zhang, K. Li, Q. Tian, and Y. Lin, "Adversarial threats to automatic modulation open set recognition in wireless networks," arXiv:2405.05022, 2024.',
 "R082": 'W. Wang, H. Liao, and L. Gan, "Open-set RF fingerprinting via improved prototype learning," arXiv:2306.13895, 2023.',
 "R083": 'S. R. Shebert, B. H. Kirk, and R. M. Buehrer, "Open set wireless signal classification: Augmenting deep learning with expert feature classifiers," arXiv:2302.03749, 2023.',
 "R084": 'X. Chen, Z. Zhao, X. Ye, S. Zheng, C. Lou, and X. Yang, "Efficient open-set recognition for interference signals based on convolutional prototype learning," *Appl. Sci.*, vol. 12, no. 9, art. 4380, 2022, doi: 10.3390/app12094380.',
 "R085": 'Y. Zhou, S. Shang, X. Song, S. Zhang, T. You *et al.*, "Intelligent radar jamming recognition in open set environment based on deep learning networks," *Remote Sens.*, vol. 14, no. 24, art. 6220, 2022, doi: 10.3390/rs14246220.',
 "R086": 'Y. Xiao, R. Zhang, X. Yu, and Y. Jiang, "Open-set recognition of compound jamming signal based on multi-task multi-label learning," *IET Radar Sonar Navig.*, vol. 18, no. 8, pp. 1235–1246, 2024, doi: 10.1049/rsn2.12561.',
 "R087": 'M. Ouyang, "An open-set jamming signal recognition method based on domain-specific network," *IET Commun.*, vol. 20, no. 1, art. e70198, 2026, doi: 10.1049/cmu2.70198.',
 "R088": 'Y. Liu, S. Han, Z. Lin, C. Guo, Q. Zhao, W. Chen, and T. Qiu, "An open-set recognition method for active radar jamming signals based on multi-dimensional prototype feature constraints and adversarial reciprocal point learning," Preprints.org, 2025, doi: 10.20944/preprints202503.2079.v1 (not peer-reviewed).',
 "R089": 'L. Henneke and F. Kurth, "Approaching domain generalization with embeddings for robust discrimination and recognition of RF communication signals," arXiv:2510.23186, 2025.',
 "R090": 'A. Bara, L. Bariah, H. Zou, B. Mefgouda, and M. Debbah, "RF-Analyzer: Can vision-language models learn RF understanding from synthetic data?," arXiv:2605.04676, 2026.',
 "R091": 'T. Chen and C. Guestrin, "XGBoost: A scalable tree boosting system," in *Proc. ACM SIGKDD*, 2016, pp. 785–794, doi: 10.1145/2939672.2939785.',
 "R092": 'SnT SmartSpace project, University of Luxembourg, "Satellite On-board Interference," dataset, n.d. [Online]. Available: https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/ (research-only, non-commercial use statement).',
 "R093": 'SnT SmartSpace project, University of Luxembourg, "NGSO to GSO\'s Users Interference," dataset, n.d. [Online]. Available: https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/ (research-only, non-commercial use statement).',
 "R094": 'F. Ott, L. Heublein, N. L. Raichur, and A. Rügamer, "GNSS Interference Spectrum Highway Dataset 1," IEEE DataPort, Oct. 31, 2024, doi: 10.21227/xpm9-tt28 (licence statements conflicting; see Appendix B).',
 "R095": 'Fraunhofer IIS, GNSS interference datasets on Zenodo: "Spectrum Highway Dataset 2 for Interference Classification in GNSS Data," record 21336653; "Spectrum & Low-Cost (LC) Laboratory Dataset for Interference Classification in GNSS Data," record 21333335; "Jammertest 2025 GNSS Interference Dataset," record 21332689 (creators and licences per record).',
 "R096": 'scikit-learn developers, "Common pitfalls and recommended practices," scikit-learn user guide, accessed Oct. 23, 2026. [Online]. Available: https://scikit-learn.org/stable/common_pitfalls.html',
 "R097": 'ETSI, "Digital Video Broadcasting (DVB); Second generation framing structure, channel coding and modulation systems for Broadcasting, Interactive Services, News Gathering and other broadband satellite applications; Part 1: DVB-S2," ETSI EN 302 307-1 V1.4.1, Nov. 2014, Annex H.',
 "R098": 'R. Liu, W. Zhu, S. Sun, and W. Zhang, "Low-latency terrestrial interference detection for satellite-to-device communications," arXiv:2506.12908, 2025.',
 "R099": 'V. Ivanov, M. Scaramuzza, and R. C. Wilson, "Deep temporal semi-supervised one-class classification for GNSS radio frequency interference detection," *J. Navigation*, vol. 77, no. 1, pp. 59–81, 2024, doi: 10.1017/S0373463324000134.',
 "R100": 'L. Heublein, T. Feigl, A. Rügamer, and F. Ott, "Achieving generalization in orchestrating GNSS interference monitoring stations through pseudo-labeling," in *Proc. POSNAV*, 2024, arXiv:2410.14686.',
 "R101": 'D. Hendrycks, M. Mazeika, and T. Dietterich, "Deep anomaly detection with outlier exposure," in *Proc. ICLR*, 2019, arXiv:1812.04606.',
 "R102": 'D. Estévez, "Test of gr4-packet-modem through an Intelsat 37e C-band transponder," Zenodo dataset, v1, Sep. 2024, doi: 10.5281/zenodo.13371136.',
 "R103": 'P. Zhao, N. Chen, Y. Li, and C. Feng, "Cross-polarization interference cancellation in satellite communication," in *Proc. EEI*, 2023, pp. 391–395, doi: 10.1109/EEI59236.2023.10212784.',
 "R104": 'TorchDSP, "TorchSig," software documentation (README), accessed Oct. 23, 2026. [Online]. Available: https://github.com/TorchDSP/torchsig',
 "R105": 'S. Kaufman, S. Rosset, C. Perlich, and O. Stitelman, "Leakage in data mining: Formulation, detection, and avoidance," *ACM Trans. Knowl. Discov. Data*, vol. 6, no. 4, art. 15, 2012, doi: 10.1145/2382577.2382579.',
 "R106": 'C. Hao, D. Feng, Q. Zhang, and X.-G. Xia, "Interference geolocation in satellite communications systems: An overview," *IEEE Veh. Technol. Mag.*, vol. 16, no. 1, pp. 66–74, Mar. 2021, doi: 10.1109/MVT.2020.3002525.',
}

# New references added in V4.3.
NEW = {
 "N001": dict(cit='K. C. Ho and Y. T. Chan, "Geolocation of a known altitude object from TDOA and FDOA measurements," *IEEE Trans. Aerosp. Electron. Syst.*, vol. 33, no. 3, pp. 770–783, 1997, doi: 10.1109/7.599239.', state="verified_publisher_metadata", ev="https://ieeexplore.ieee.org/document/599239", src="RF-search C02", typ="journal"),
 "N002": dict(cit='A. Kalantari, S. Maleki, S. Chatzinotas, and B. Ottersten, "Frequency of arrival-based interference localization using a single satellite," in *Proc. ASMS/SPSC*, 2016, arXiv:1608.00350.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/1608.00350", src="RF-search C03", typ="conference"),
 "N003": dict(cit='I. Glendinning, M. Nölle, C. Hausleitner, and E. Greilinger, "Identification of the source of an interferer by comparison with known carriers using a single satellite," arXiv:1805.06567, 2018 (journal version: *Int. J. Satell. Commun. Netw.*, 2019).', state="verified_publisher_metadata", ev="https://arxiv.org/abs/1805.06567", src="RF-search C04", typ="preprint/journal"),
 "N004": dict(cit='A. Pastukh, V. Tikhvinskiy, E. Devyatkin, and A. Kostin, "Interference analysis of 5G NR base stations to fixed satellite service bent-pipe transponders in the 6425–7125 MHz frequency band," *Sensors*, vol. 23, no. 1, art. 172, 2023, doi: 10.3390/s23010172.', state="verified_publisher_metadata", ev="https://www.mdpi.com/1424-8220/23/1/172", src="RF-search C05", typ="journal"),
 "N005": dict(cit='A. Mehboob, K. J. Layton, G. Lechner, and W. G. Cowley, "Wiener predistorter for nonlinear satellite downlinks," *Int. J. Satell. Commun. Netw.*, vol. 41, no. 4, pp. 392–405, 2023, doi: 10.1002/sat.1474.', state="verified_publisher_metadata", ev="https://onlinelibrary.wiley.com/doi/10.1002/sat.1474", src="RF-search C14", typ="journal"),
 "N006": dict(cit='ITU-R, "Carrier-to-interference calculations between networks in the fixed-satellite service," Recommendation ITU-R S.741-2, Sep. 1994.', state="verified_publisher_metadata", ev="https://www.itu.int/rec/R-REC-S.741-2-199409-I/en", src="RF-search C20", typ="standard"),
 "N007": dict(cit='ITU-R, "Apportionment of the allowable error performance degradations to fixed-satellite service (FSS) hypothetical reference digital paths arising from time invariant interference for systems operating below 30 GHz," Recommendation ITU-R S.1432-1, Apr. 2006.', state="verified_publisher_metadata", ev="https://www.itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.1432-1-200604-I!!PDF-E.pdf", src="RF-search C17", typ="standard"),
 "N008": dict(cit='R. Peters, P. Woolner, and E. Ekelman, "Analytic calculation of noise power robbing, NPR, and polarization isolation degradation," NASA Technical Reports Server, document 20080023297, 2008.', state="verified_publisher_metadata", ev="https://ntrs.nasa.gov/citations/20080023297", src="RF-search C08", typ="technical report"),
 "N009": dict(cit='Rohde & Schwarz, "Noise power ratio (NPR) measurement," technical web resource, n.d. [Online]. Available: https://www.rohde-schwarz.com/nl/_258365.html', state="verified_publisher_metadata", ev="https://www.rohde-schwarz.com/nl/_258365.html", src="RF-search C10", typ="vendor technical note"),
 "N010": dict(cit='ITU-R, "Definition and measurement of intermodulation products in transmitters using frequency, time, or code domain multiple access techniques," Recommendation ITU-R SM.1446-0, Apr. 2000.', state="secondary_only", ev="https://www.itu.int/dms_pubrec/itu-r/rec/sm/R-REC-SM.1446-0-200004-I!!PDF-E.pdf", src="STD-search STD08 (search excerpt only)", typ="standard"),
 "N011": dict(cit='ETSI, "Digital Video Broadcasting (DVB); Framing structure, channel coding and modulation of a carrier identification system (DVB-CID) for satellite transmission," ETSI TS 103 129 V1.1.2.', state="secondary_only", ev="repository records P18_b2_protocol.md:57; B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md:290 (Table 6 inspected by the project; standard text not in repository)", src="repository context; batch-1 notes on CID level range", typ="standard"),
 "N012": dict(cit='ITU-R, Recommendation ITU-R S.728-1, "Maximum permissible level of off-axis e.i.r.p. density from very small aperture terminals (VSATs)," Oct. 1995.', state="secondary_only", ev="https://itu.int/dms_pubrec/itu-r/rec/s/R-REC-S.728-1-199510-I!!PDF-E.pdf", src="RF-search C18", typ="standard"),
 "N013": dict(cit='Feder *et al.*, "Blind carrier and noise power and roll-off factor estimation for PCMA signals," open-access article, 2025, KIT repository record publikationen.bibliothek.kit.edu/1000188823 (full bibliographic details not confirmed in this audit).', state="secondary_only", ev="https://publikationen.bibliothek.kit.edu/1000188823", src="audit search AUD-01", typ="journal (unconfirmed)"),
 "N014": dict(cit='S. Dimitrov *et al.*, "Design and implementation of transparent cross-polarization interference compensation in a wideband dual-polarization satellite receiver," *Int. J. Satell. Commun. Netw.*, vol. 42, no. 6, pp. 481–492, 2024, doi: 10.1002/sat.1533.', state="verified_publisher_metadata", ev="https://onlinelibrary.wiley.com/doi/abs/10.1002/sat.1533", src="STD-search STD09; audit search AUD-02", typ="journal"),
 "N015": dict(cit='O. Ulubey, S. Gulgonul, and A. Kara, "Characterization of satellite transponder impairments based on simulations with test data," in *Proc. 7th Int. Conf. Recent Advances in Space Technologies (RAST)*, Istanbul, 2015, pp. 373–378, doi: 10.1109/RAST.2015.7208372.', state="secondary_only", ev="https://ada.atilim.edu.tr/entities/publication/452387e1-b7f1-43f0-b25b-9a07880a2d05", src="RF-search C09", typ="conference"),
 "N016": dict(cit='C. Yang, B. Yang, K. Qiu, Z. Chen, and Y. Gao, "DualAttWaveNet: Multiscale attention networks for satellite interference detection," arXiv:2504.17187, 2025.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2504.17187", src="ML-search C01", typ="preprint"),
 "N017": dict(cit='"An efficient way for satellite interference signal recognition via incremental learning," IEEE conference paper, IEEE Xplore document 8909134.', state="secondary_only", ev="https://ieeexplore.ieee.org/document/8909134", src="ML-search C05", typ="conference"),
 "N018": dict(cit='"Method and device for determining if at least one interferer generated by cross polarization interference is present in received frame," U.S. Patent 9,929,797.', state="unverified", ev="https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9929797", src="ML-search C07", typ="patent"),
 "N019": dict(cit='R. Kamoi and K. Kobayashi, "Why is the Mahalanobis distance effective for anomaly detection?," arXiv:2003.00402, 2020.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2003.00402", src="ML-search C15", typ="preprint"),
 "N020": dict(cit='J. Ren, S. Fort, J. Liu, A. G. Roy, S. Padhy, and B. Lakshminarayanan, "A simple fix to Mahalanobis distance for improving near-OOD detection," arXiv:2106.09022, 2021.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2106.09022", src="ML-search C16", typ="preprint/workshop"),
 "N021": dict(cit='Y. Sun, Y. Ming, X. Zhu, and Y. Li, "Out-of-distribution detection with deep nearest neighbors," in *Proc. ICML*, PMLR, 2022, pp. 20827–20840.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2204.06507", src="ML-search C20", typ="conference"),
 "N022": dict(cit='J. Zhang *et al.*, "OpenOOD v1.5: Enhanced benchmark for out-of-distribution detection," arXiv:2306.09301, 2023.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2306.09301", src="ML-search C21", typ="preprint"),
 "N023": dict(cit='Y. L. Li, D. Lu, P. Kirichenko, S. Qiu, T. G. J. Rudner, C. B. Bruss, and A. G. Wilson, "Position: Supervised classifiers answer the wrong questions for OOD detection," in *Proc. ICML*, PMLR vol. 267, 2025 (extended version arXiv:2507.01831).', state="verified_publisher_metadata", ev="https://proceedings.mlr.press/v267/li25ec.html", src="ML-search C23", typ="conference"),
 "N024": dict(cit='J. Bitterwolf *et al.*, "In or out? Fixing ImageNet out-of-distribution detection evaluation," in *Proc. ICML*, PMLR vol. 202, 2023, pp. 2471–2506.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2306.00826", src="ML-search C24", typ="conference"),
 "N025": dict(cit='A. Palechor, A. Bhoumik, and M. Günther, "Large-scale open-set classification protocols for ImageNet," in *Proc. IEEE/CVF WACV*, 2023, pp. 42–51.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2210.06789", src="ML-search C25", typ="conference"),
 "N026": dict(cit='H. Wang, S. Vaze, and K. Han, "Dissecting out-of-distribution detection and open-set recognition: A critical analysis of methods and benchmarks," arXiv:2408.16757, 2024.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2408.16757", src="ML-search C27", typ="preprint"),
 "N027": dict(cit='C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in *Proc. ICML*, PMLR vol. 70, 2017, pp. 1321–1330.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/1706.04599", src="ML-search C28", typ="conference"),
 "N028": dict(cit='Y. Ovadia, E. Fertig, J. Ren, Z. Nado, D. Sculley, S. Nowozin, J. Dillon, B. Lakshminarayanan, and J. Snoek, "Can you trust your model\'s uncertainty? Evaluating predictive uncertainty under dataset shift," in *Proc. NeurIPS*, 2019.', state="verified_publisher_metadata", ev="https://papers.nips.cc/paper/2019/hash/8558cb408c1d76621371888657d2eb1d-Abstract.html", src="ML-search C29", typ="conference"),
 "N029": dict(cit='Y. Geifman and R. El-Yaniv, "Selective classification for deep neural networks," in *Proc. NeurIPS*, 2017, arXiv:1705.08500.', state="verified_publisher_metadata", ev="https://arxiv.org/abs/1705.08500", src="ML-search C30", typ="conference"),
 "N030": dict(cit='"Out-of-distribution (OOD) detectors for open-set RF fingerprinting," arXiv:2606.12718, 2026 (authors not confirmed in this audit).', state="verified_publisher_metadata", ev="https://arxiv.org/abs/2606.12718", src="ML-search C12", typ="preprint"),
 "N032": dict(cit='O. Shimbo, "Effects of intermodulation, AM-PM conversion, and additive noise in multicarrier TWT systems," *Proc. IEEE*, vol. 59, no. 2, pp. 230–238, Feb. 1971.', state="secondary_only", ev="cited-by and repository records in RF search (RF-search C12)", src="RF-search C12 (re-included after red-team RT-17/RT-36)", typ="journal"),
 "N033": dict(cit='S. Benedetto, E. Biglieri, and R. Daffara, "Modeling and performance evaluation of nonlinear satellite links—A Volterra series approach," *IEEE Trans. Aerosp. Electron. Syst.*, vol. AES-15, no. 4, pp. 494–507, Jul. 1979.', state="secondary_only", ev="cited-by records in RF search (RF-search C15)", src="RF-search C15 (re-included after red-team RT-36)", typ="journal"),
 "N034": dict(cit='W. J. Scheirer, A. de Rezende Rocha, A. Sapkota, and T. E. Boult, "Toward open set recognition," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 35, no. 7, pp. 1757–1772, 2013, doi: 10.1109/TPAMI.2012.256.', state="unverified", ev="added from domain knowledge after red-team RT-36; not checked (search budget exhausted)", src="red-team addition", typ="journal"),
 "N035": dict(cit='R. Tandra and A. Sahai, "SNR walls for signal detection," *IEEE J. Sel. Topics Signal Process.*, vol. 2, no. 1, pp. 4–17, Feb. 2008, doi: 10.1109/JSTSP.2007.914879.', state="unverified", ev="added from domain knowledge after red-team RT-35; not checked (search budget exhausted)", src="red-team addition", typ="journal"),
 "N036": dict(cit='M. Basseville and I. V. Nikiforov, *Detection of Abrupt Changes: Theory and Application*. Englewood Cliffs, NJ, USA: Prentice Hall, 1993.', state="unverified", ev="added from domain knowledge after red-team RT-02; not checked", src="red-team addition", typ="book"),
 "N037": dict(cit='J. J. Gertler, *Fault Detection and Diagnosis in Engineering Systems*. New York, NY, USA: Marcel Dekker, 1998.', state="unverified", ev="added from domain knowledge after red-team RT-02; not checked", src="red-team addition", typ="book"),
 "N038": dict(cit='G. Maral, M. Bousquet, and Z. Sun, *Satellite Communications Systems: Systems, Techniques and Technology*, 6th ed. Chichester, U.K.: Wiley, 2020.', state="unverified", ev="added from domain knowledge after red-team RT-02; edition details not checked", src="red-team addition", typ="book"),
 "N039": dict(cit='ITU-R, "Reference radiation pattern of earth station antennas in the fixed-satellite service for use in coordination and interference assessment in the frequency range from 2 to 31 GHz," Recommendation ITU-R S.465-6, Jan. 2010.', state="secondary_only", ev="repository record docs/plan/P18_b2_protocol.md (ASI geometry uses S.465-6); standard text not opened", src="repository context", typ="standard"),
 "N031": dict(cit='D. P. Haworth, N. G. Smith, R. Bardelli, and T. Clement, "Interference localization for EUTELSAT satellites—the first European transmitter location system," *Int. J. Satell. Commun.*, vol. 15, no. 4, pp. 155–183, 1997.', state="secondary_only", ev="cited-by records (arXiv:1608.00350 reference list)", src="RF-search C01", typ="journal"),
}

# Audit outcome overrides for legacy references (state, note). Defaults come from verification CSVs.
OVR = {
 "R007": ("verified_publisher_metadata", "Journal version located (IEEE SPM 36(4), 2019) via institutional repository; citation updated from arXiv; author order kept from the preprint and to be confirmed against IEEE Xplore."),
 "R008": ("verified_publisher_metadata", "Claim corrected: SPAWC 2016 cancels known pilot symbols; decoded-signal cancellation is R009."),
 "R014": ("verified_publisher_metadata", "CID level is a range (about 17.5–27.5 dB below host PSD depending on host symbol rate); fixed 27.5 dB statement removed; vendor-authored."),
 "R024": ("unverified", "Title and arXiv identifier confirmed via search excerpt (PDF URL); authors and reported figures not re-inspected in this audit; previous revision reports a primary-text check of the figures."),
 "R029": ("verified_publisher_metadata", "Published version (Intelligent and Converged Networks 2021) substituted for arXiv preprint."),
 "R030": ("verified_publisher_metadata", "Published version (IEEE COMST 2025) substituted for repository preprint."),
 "R038": ("secondary_only", "Original citation contradicted (title said 'jamming'); corrected record confirmed by institutional repository (PoliTo IRIS). Title corrected to 'GNSS interference and jammer'; volume/issue/pages not confirmed (early-access pages differ); DOI matches."),
 "R043": ("verified_publisher_metadata", "Sixth author added; IEEE TVT 2021 version substituted for arXiv preprint."),
 "R046": ("verified_publisher_metadata", "arXiv v1 and v2 differ in title/authors; v2 cited; possible journal version not confirmed."),
 "R047": ("verified_publisher_metadata", "Published version (IEEE Access 2022) substituted; not cited in V4.3 text because the open-set claim could not be confirmed."),
 "R090": ("verified_publisher_metadata", "Claim corrected: the source reports that synthetic-trained VLMs generalize to real signals; now cited as mixed/contrary transfer evidence."),
 "R095": ("verified_primary_dataset_record", "Combined title split into three Zenodo records with exact titles; licences per record; creators not visible."),
 "R106": ("verified_publisher_metadata", "Re-found on IEEE Xplore (document 9138454) in the RF search; year 2021 (DOI registered 2020)."),
 "R051": ("secondary_only", "Checked in the standards stream: metadata and model form confirmed via Semantic Scholar and software documentation; coefficient provenance (4.0033 vs 4.033) unresolved; IEEE page not seen."),
 "R054": ("verified_publisher_metadata", "Official ETSI V1.2.1 (2021-01) PDF listing and DVB A171-2 drafts confirmed in the standards stream; §4.4.1.3 three-term cross-polar model and example values seen at search-excerpt level (V1.1.1 text and V1.2.1 draft); previous revision reports full-text inspection of V1.2.1."),
 "R097": ("verified_publisher_metadata", "Official ETSI V1.4.1 (2014-11) PDF listing confirmed; Annex H 'examples of possible use' with H.7 transponder models seen in search excerpts; informative status and figure numbering rely on a previous revision's inspection."),
 "R056": ("secondary_only", "Institutional repository record matches all fields including DOI; also re-found in RF search."),
}

# References excluded from the V4.3 text with reason.
EXCLUDED = {
 "R031": "Searched three times in this audit without a confirming record; not needed for any claim (survey list kept to R029, R030).",
 "R044": "No trace of the cited Cyclo-AMC paper found in two searches; the supporting sentence was removed rather than relying on an unconfirmed source.",
 "R047": "Claim that the survey identifies open-set recognition as under-studied could not be confirmed from accessible abstracts; claim removed.",
 "N010": "Dropped after red-team RT-17: secondary excerpt of a transmitter-IM measurement recommendation is indirect support for the satellite C/IM slope; replaced by N032 and R058.",
 "N013": "Dropped after red-team RT-19/RT-44: author initials, venue and year could not be confirmed.",
 "N030": "Dropped after red-team RT-19: authors not confirmed and the source concerns emitter identity, not interference families.",
 "R057": "Existence not confirmed in this audit (only an aggregator link); NPR statement now relies on an NTRS report and a technical note.",
}


def load_states():
    st, sup = {}, {}
    for f in glob.glob(os.path.join(SCR, "verify", "out_batch*.csv")):
        for row in csv.DictReader(open(f, encoding="utf-8")):
            st[row["stable_id"]] = row
    return st


def legacy_status():
    d = {}
    for x in json.load(open(os.path.join(REPO, "refs.json"))):
        d["R%03d" % x["n"]] = x["status"]
    return d


def build():
    rows = load_states()
    leg = legacy_status()
    recon = {e["stable_id"]: e for e in json.load(open(os.path.join(REPO, "reference_reconciliation_v4_1.json")))["entries"]}
    db = {}
    for sid, cit in CIT.items():
        r = rows.get(sid, {})
        state = r.get("verification_state", "unverified") or "unverified"
        note = r.get("discrepancies", "")
        if sid in OVR:
            state, note = OVR[sid][0], OVR[sid][1]
        db[sid] = dict(sid=sid, cit=cit, state=state, note=note, legacy_status=leg.get(sid, "not in refs.json (added in later revision)"),
                       v41_number=recon.get(sid, {}).get("publication_number"), original_number=recon.get(sid, {}).get("original_number"),
                       evidence=r.get("evidence_urls", ""), claim_support=r.get("claim_support", ""), claim_evidence=r.get("claim_support_evidence", ""),
                       content=r.get("content_summary", ""), queries=r.get("queries_run", ""), origin="legacy",
                       not_searched=(r.get("queries_run", "").strip() == "" or "not searched" in (r.get("discrepancies", "") + r.get("queries_run", "")).lower()))
    for sid, v in NEW.items():
        db[sid] = dict(sid=sid, cit=v["cit"], state=v["state"], note="New in V4.3 (" + v["src"] + ")", legacy_status="new", v41_number=None, original_number=None,
                       evidence=v["ev"], claim_support="", claim_evidence="", content="", queries=v["src"], origin="new", not_searched=False, typ=v["typ"])
    return db


STATE_LABEL = {
 "verified_full_text": "full text verified",
 "verified_publisher_metadata": "publisher/registry metadata verified",
 "verified_primary_dataset_record": "primary dataset record verified",
 "secondary_only": "secondary record only",
 "unverified": "not verified in this audit",
 "contradicted": "metadata corrected (contradicted)",
}
