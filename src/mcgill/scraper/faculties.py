"""McGill faculty and department registry."""

from __future__ import annotations

ALL_FACULTIES: list[tuple[str, str, list[str]]] = [
    ("Agricultural & Environmental Sciences", "agri-env-sci", [
        "AGRI", "ANSC", "BIEN", "FDSC", "FMGT", "PARA", "PLNT",
        "NRSC", "AEBI", "AEMA", "ABEN", "LSCI",
    ]),
    ("Arts", "arts", [
        "ANTH", "ARTH", "CANS", "CLAS", "EAST", "ECON", "ENGL",
        "PHIL", "POLI", "PSYC", "RELG", "RELI", "HIST", "ISLA",
        "LING", "JWST", "SOCI", "SWRK", "URBS", "INTD", "WMST",
        "GERM", "SPAN", "ITAL", "PORT", "RUSS", "CHIN", "JPST", "ARAB", "HEBR",
    ]),
    ("Dental Medicine & Oral Health Sciences", "dental", [
        "DENT", "MDNT", "ORCD",
    ]),
    ("Education", "education", [
        "EDEC", "EDPE", "EDST", "EDSA", "EDKN", "EDLB", "EDLS",
        "EDPL", "EDUC", "KINE",
    ]),
    ("Engineering", "engineering", [
        "ECSE", "MECH", "CIVE", "MIME", "FACC", "CHEE", "MTLS",
        "ENVE", "BREE", "MIMI", "ENGR",
    ]),
    ("Environment (Bieler School)", "environment", [
        "ENVB", "ENVR",
    ]),
    ("Law", "law", [
        "LAWS",
    ]),
    ("Management (Desautels)", "management", [
        "ACCT", "FINE", "INSY", "MGCR", "MGMT", "MRKT", "ORGB",
        "STRA", "BUSA",
    ]),
    ("Medicine & Health Sciences", "medicine", [
        "ANAT", "BIOC", "EPIB", "EXMD", "MEDC", "MICR", "NSCI",
        "NEUR", "PHAR", "PHGY", "PTOT", "REHB", "ORTH", "MDCN", "NUTR", "SPCH",
    ]),
    ("Music (Schulich)", "music", [
        "MUAR", "MUSP", "MUTH",
    ]),
    ("Nursing", "nursing", [
        "NURS",
    ]),
    ("Science", "science", [
        "ATOC", "BIOL", "CHEM", "COMP", "EART", "GEOG", "MATH",
        "PHYS", "PSYC", "ANAT", "BIOC", "MICR", "PHAR", "PHGY", "NRSC",
    ]),
]

PROGRAM_PAGES: dict[str, list[str]] = {
    "agri-env-sci": [
        "/en/undergraduate/agri-env-sci/",
        "/en/undergraduate/agri-env-sci/programs/",
        "/en/undergraduate/agri-env-sci/programs/animal-science/",
        "/en/undergraduate/agri-env-sci/programs/food-science-agricultural-chemistry/",
        "/en/undergraduate/agri-env-sci/programs/natural-resource-sciences/",
        "/en/undergraduate/agri-env-sci/programs/plant-science/",
        "/en/undergraduate/agri-env-sci/programs/bioresource-engineering/",
        "/en/undergraduate/agri-env-sci/programs/human-nutrition/",
        "/en/graduate/agri-env-sci/",
        "/en/graduate/agri-env-sci/food-science-agricultural-chemistry/",
    ],
    "arts": [
        "/en/undergraduate/arts/",
        "/en/undergraduate/arts/programs/",
        "/en/undergraduate/arts/programs/economics/",
        "/en/undergraduate/arts/programs/political-science/",
        "/en/undergraduate/arts/programs/psychology/",
        "/en/undergraduate/arts/programs/sociology/",
        "/en/undergraduate/arts/programs/history/",
        "/en/undergraduate/arts/programs/philosophy/",
        "/en/undergraduate/arts/programs/linguistics/",
        "/en/graduate/arts/",
    ],
    "dental": [
        "/en/undergraduate/dental/",
        "/en/graduate/dental/",
    ],
    "education": [
        "/en/undergraduate/education/",
        "/en/undergraduate/education/programs/",
        "/en/graduate/education/",
    ],
    "engineering": [
        "/en/undergraduate/engineering/",
        "/en/undergraduate/engineering/programs/",
        "/en/undergraduate/engineering/programs/electrical-computer/",
        "/en/undergraduate/engineering/programs/mechanical/",
        "/en/undergraduate/engineering/programs/civil/",
        "/en/undergraduate/engineering/programs/chemical/",
        "/en/undergraduate/engineering/programs/materials/",
        "/en/graduate/engineering/",
    ],
    "environment": [
        "/en/undergraduate/environment/",
        "/en/graduate/environment/",
    ],
    "law": [
        "/en/undergraduate/law/",
        "/en/graduate/law/",
    ],
    "management": [
        "/en/undergraduate/management/",
        "/en/undergraduate/management/programs/",
        "/en/graduate/management/",
    ],
    "medicine": [
        "/en/undergraduate/medicine/",
        "/en/graduate/medicine/",
        "/en/graduate/medicine/biochemistry/",
        "/en/graduate/medicine/epidemiology-biostatistics/",
        "/en/graduate/medicine/microbiology-immunology/",
        "/en/graduate/medicine/pharmacology-therapeutics/",
        "/en/graduate/medicine/physiology/",
        "/en/graduate/medicine/neuroscience/",
    ],
    "music": [
        "/en/undergraduate/music/",
        "/en/graduate/music/",
    ],
    "nursing": [
        "/en/undergraduate/nursing/",
        "/en/graduate/nursing/",
    ],
    "science": [
        "/en/undergraduate/science/",
        "/en/undergraduate/science/programs/",
        "/en/undergraduate/science/programs/biology/",
        "/en/undergraduate/science/programs/chemistry-programs/",
        "/en/undergraduate/science/programs/computer-science-programs/",
        "/en/undergraduate/science/programs/mathematics-statistics-programs/",
        "/en/undergraduate/science/programs/physics/",
        "/en/undergraduate/science/programs/psychology-programs/",
        "/en/undergraduate/science/programs/biochemistry-programs/",
        "/en/undergraduate/science/programs/microbiology-immunology/",
        "/en/undergraduate/science/programs/earth-planetary-sciences/",
        "/en/graduate/science/",
        "/en/graduate/science/biology/",
        "/en/graduate/science/chemistry/",
        "/en/graduate/science/computer-science/",
        "/en/graduate/science/mathematics-statistics/",
        "/en/graduate/science/physics/",
        "/en/graduate/science/psychology/",
    ],
}


def get_active_faculties(
    faculty_filter: list[str] | None = None,
) -> list[tuple[str, str, list[str]]]:
    if faculty_filter is None:
        return ALL_FACULTIES
    allowed = {v.lower() for v in faculty_filter}
    return [f for f in ALL_FACULTIES if f[0].lower() in allowed or f[1].lower() in allowed]
