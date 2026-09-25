"""Bancos de frases usados pelo roteador (estágio 2), descritores (estágio 3) e validação."""

# v1: só achados suspeitos, score = similaridade máxima
BANCO_V1 = [
    "tumor nests",
    "necrosis",
    "high nuclear pleomorphism",
    "mitotic figures",
    "dense atypical stroma",
]

# v2: benigno vs. suspeito, score = margem (suspeito - benigno)
BANCO_V2 = {
    "benigno": [
        "normal duct epithelium",
        "normal lobular tissue",
        "adipose tissue",
        "benign fibrous stroma",
        "usual ductal hyperplasia",
    ],
    "suspeito": [
        "tumor nests",
        "necrosis",
        "comedonecrosis",
        "high nuclear pleomorphism",
        "nuclear crowding and stratification",
        "mitotic figures",
        "cribriform architecture",
        "micropapillary architecture",
        "solid growth pattern",
        "stromal invasion",
        "desmoplastic stroma",
    ],
}

# Um banco por classe BRACS, com critério diagnóstico padrão (OMS / critérios de Page).
# ADH, DCIS e IC são os mesmos usados antes na BRACS_748; N, PB, UDH e FEA foram
# adicionados porque as lâminas novas têm essas classes.
BANCO_POR_CLASSE = {
    "N": [
        "normal breast tissue",
        "normal terminal duct lobular unit",
        "normal duct with luminal and myoepithelial cell layers",
        "unremarkable breast lobules",
        "normal breast parenchyma",
    ],
    "PB": [
        "fibroadenoma",
        "fibrocystic change",
        "sclerosing adenosis",
        "apocrine metaplasia",
        "cystically dilated ducts",
    ],
    "UDH": [
        "usual ductal hyperplasia",
        "streaming heterogeneous epithelial cells",
        "irregular slit-like fenestrations",
        "overlapping nuclei without atypia",
        "benign epithelial hyperplasia",
    ],
    "FEA": [
        "flat epithelial atypia",
        "dilated acini lined by atypical columnar cells",
        "columnar cell lesion with atypia",
        "monotonous cuboidal cells lining dilated acini",
        "apical snouts in columnar cells",
    ],
    "ADH": [
        "atypical ductal hyperplasia",
        "focal atypical epithelial proliferation",
        "mild nuclear atypia",
        "monomorphic epithelial cell population",
        "partial duct involvement by atypical cells",
    ],
    "DCIS": [
        "ductal carcinoma in situ",
        "intraductal proliferation with preserved basement membrane",
        "comedonecrosis",
        "cribriform intraductal pattern",
        "intact myoepithelial cell layer",
    ],
    "IC": [
        "invasive carcinoma",
        "stromal invasion",
        "loss of myoepithelial cell layer",
        "desmoplastic stromal reaction",
        "infiltrating tumor cells within stroma",
    ],
}

# Categorias oficiais do BRACS (ver docs/datasets.md): benigno = N, PB; atípico = UDH, FEA, ADH;
# maligno = DCIS, IC.
CATEGORIA_DA_CLASSE = {"N": "benigno", "PB": "benigno", "UDH": "atipico", "FEA": "atipico",
                       "ADH": "atipico", "DCIS": "maligno", "IC": "maligno"}


def _sem_repetir(*listas):
    vistas, saida = set(), []
    for lista in listas:
        for f in lista:
            if f not in vistas:
                vistas.add(f)
                saida.append(f)
    return saida


# Banco do descritor (estágio 3): o espectro inteiro, pra que um patch de tecido normal possa
# ser descrito como normal. Antes o descritor só tinha frases suspeitas (BANCO_V2["suspeito"])
# e descrevia até tecido normal como "desmoplastic stroma, stromal invasion".
BANCO_DESCRITOR = {
    "benigno": _sem_repetir(BANCO_POR_CLASSE["N"], BANCO_POR_CLASSE["PB"],
                            ["adipose tissue", "benign fibrous stroma"]),
    "atipico": _sem_repetir(BANCO_POR_CLASSE["UDH"], BANCO_POR_CLASSE["FEA"], BANCO_POR_CLASSE["ADH"]),
    "maligno": _sem_repetir(BANCO_V2["suspeito"], BANCO_POR_CLASSE["DCIS"], BANCO_POR_CLASSE["IC"]),
}

# Ensemble de prompts (sugestão do Prof. João): várias formulações por frase, média dos embeddings.
TEMPLATES_ENSEMBLE = [
    "{}",
    "histopathology image showing {}",
    "H&E stained tissue with {}",
    "microscopic image of {}",
    "a tissue patch with {}",
]
