"""
gt_name_corrections.py — Speaker name normalization for Guatemala PDFs.

Python equivalent of the name correction block in GTM_Rodrigo.R (lines 345–681),
translated faithfully with the following differences:
  - Unicode stripping uses unicodedata (same result as stri_trans_general latin-ascii)
  - Order of corrections preserved exactly (later entries override earlier ones)
  - Conditional corrections (date/legislature/speaker-dependent) implemented as
    a dispatch function

Usage:
    from lib.utils.gt_name_corrections import normalize_speaker, correct_nm_fuse
"""

import re
import unicodedata
from datetime import date


# ── ASCII transliteration ──────────────────────────────────────────────────────

def to_ascii_upper(s: str) -> str:
    """Equivalent to R: stri_trans_general(s, 'latin-ascii') |> toupper()."""
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()


# ── Prefix and role title stripping ───────────────────────────────────────────
# Equivalent to R lines 349–368 (PREFIX_STRIPS + err vector)

_PREFIX_PATTERNS = [
    r'^EL R\. ',
    r'^LA R\. ',
    r'^DIPUTADO ',
    r'^DIPUTADA ',
    r'^EL DIPUTADO ELECTO ',
    r'^EL DIPUTADO ',
    r'^LA DIPUTADA ELECTA ',
    r'^LA DIPUTADA ',
]

_ROLE_PATTERNS = [
    r', EN FUNCIONES DE PRESIDENT[EA]?E?',
    r', EN FUNCIONES DE PRESIDNETE',
    r', EN FUNCINES DE PRESIDENTE',
    r', EN FUNCION DE PRESIDENTE',
    r', EN FUNCIONE DE PRESIDENTE',
    r', EN FUNCIONES DE PRESDIENTE',
    r', EN FUNCIONES DE PRSIDENTE',
    r', EN FUNCIONES DE RESIDENTE',
    r', EN FUNCIONES DSE PRESIDENTE',
    r', N FUNCIONES DE PRESIDENTE',
    r', PRESIDENTE EN FUNCIONES',
    r', EN FUNCIONES DE SECRETARI[AO]',
    r', EN FUCIONES DE PRESIDENTE',
    r', EN FUNCIIONES DE PRESIDENTE',
    r' EN FUNCIONES DE PRESIDENTE',
    r' DICTAMEN HONORABLE PLENO',
    r'^TERCERA VICEPRESIDENTA, ?',
    r'^TERCER VICEPRESIDENTE, ?',
    r'^VICEPRESIDENTA, ?',
    r'^VICEPRESIDENTE, ?',
    r'^SEGUNDO VICEPRESIDENTE, ?',
    r'^SEGUNDA VICEPRESIDENTE, ?',
    r'^SEGUNDA VICEPRESIDENTA, ?',
    r'^PRIMERA VICEPRESIDENTE, ?',
    r'^PRIMERA VICEPRESIDENTA, ?',
    r'^PRIMER VICEPRESIDENTE, ?',
    r'^PRIMER VICEPRESIDENTA, ?',
    r'^PRIMER VICEPRESDIENTE ',
    r'^PRIMER VICEPRESENTE ',
    r'^PRIMER VICEPRESIDENE ',
    r'^PRIMER VICEPRESIENTE ',
    r'^PRIMER VICRESIDENTE ',
    r'^PRIMER VICREPRESIDENTE ',
    r'^PPRIMER VICEPRESIDENTE ',
    r'^PRIMER VOCAL ',
    r'^PRIMER SECRETARIO ',
    r'^EL R\. PRIMER VICEPRESIDENTE ',
    r'^VOCAL I, ',
    r'^VOCAL I DE COMISION PERMANENTE, ?',
    r'^VOCAL I DE LA COMISION PERMANENETE, ',
    r'^VOCAL I DE LA COMISION PERMANENTE, ?',
    r'^VOCAL II DE LA COMISION PERMANENTE, ',
    r'^VOCAL III DE LA COMISION PERMANENTE, ',
    r'^VOCAL III, ',
    r'^VOCAL PRIM[EA]R[AO], ?',
    r'^VOCAL PRIMER ',
    r'^VOCAL RIMERO ',
    r'^VOCAL SEGUND[OA], ?',
    r'^VOCAL TERCER[OA], ?',
    r'^VOCAL PRIMERO, ',
    r'^EL SECRETARIO ',
    r'^SECRETARIO DE (?:LA )?JUNTA (?:PROVISIONAL )?DE DEBATES, ',
    r'^SECRETARIO ACCIDENTAL, ?',
    r'^SECRETARIA ACCIDENTAL, ?',
    r'^SECREATARIO ',
    r'^SECETARIO ',
    r'^SE CRETARIO ',
    r'^SECRETRIO ',
    r'^SECRETARIO, ?',
    r'^SECRETARIA, ?',
    r'^SECRETARIO ',
    r'^SECRETARIA ',
    r'^SECRETARO ',
    r'^REPRESENTANTE ',
    r'^DE LA JUNTA (?:PROVISIONAL )?DE DEBATES, ?',
    r'^DE LA COMISION PERMANENTE, ',
    r'^PRESIDENTE DE LA JUNTA (?:PROVISIONAL )?DE DEBATES, ?',
    r'^Y MIEMBRO DEL COMITE EJECUTIVO DE LA UNION INTERPARLAMENTARIA MUNDIAL, ',
    r', PRESIDENTE DE LA COMISION DE LEGISLACION Y PUNTOS CONSTITUCIONALES',
    r'^EL SENOR PRESIDENTE DE LA COMISION DE SALUD, ASISTENCIA Y SEGURIDAD SOCIAL DEL CONGRESO DE LA REPUBLICA, REPRESENTANTE ',
    r'EL SENOR PRESIDENTE DE LA COMISION LIQUIDADORA DEL BANCO NACIONAL DE LA VIVIENDA, LICENCIADO ',
    r'PRESIDENTE ACCIDENTAL ',
]


def normalize_speaker(speaker_raw: str) -> str:
    """
    Convert raw speaker string to normalized nm_fuse.
    Equivalent to R lines 345–370: ascii + upper + prefix strips.
    """
    nm = to_ascii_upper(speaker_raw)
    nm = nm.strip()
    nm = re.sub(r'\s+', ' ', nm)

    # Initial prefix strips
    for pat in _PREFIX_PATTERNS:
        nm = re.sub(pat, '', nm, count=1)

    # Special: EL SENOR PRESIDENTE DEL CONGRESO → PRESIDENTE
    nm = re.sub(
        r'^EL SENOR PRESIDENTE DEL CONGRESO DE LA REPUBLICA, ',
        'PRESIDENTE ',
        nm,
    )

    # Role title strips
    for pat in _ROLE_PATTERNS:
        nm = re.sub(pat, '', nm)

    # Strip trailing colon artifact from PDF speaker format ("NAME: text…")
    return nm.rstrip(':').strip()


# ── Simple (unconditional) corrections ────────────────────────────────────────
# Equivalent to R lines 373–607 (unconditional nm_fuse assignments).
# Format: {wrong_form: canonical_form}
# Built from a list to preserve intent; last definition wins for duplicates.

_SIMPLE_LIST = [
    # --- Block 1 (lines 373–399) ---
    ("PRESIDENTE DEL CONGRESO DE LA REPUBLICA, MEYER MALDONADO", "PRESIDENTE MEYER MALDONADO"),
    ("ALVAREZ ALVAREZ", "ALVAREZ Y ALVAREZ"),
    ("AVAREZ Y ALVAREZ", "ALVAREZ Y ALVAREZ"),
    ("ARAUZ FIQUEROA", "ARAUZ FIGUEROA"),
    ("AREVALO BARRIOS, OSWALDO", "AREVALO BARRIOS, OSWALDO IVAN"),
    ("AREVALO BARRIOS, IVAN", "AREVALO BARRIOS, OSWALDO IVAN"),
    ("AREVALO BARRIOS OSWALDO IVAN", "AREVALO BARRIOS, OSWALDO IVAN"),
    ("OSWALDO IVAN AREVALO BARRIOS", "AREVALO BARRIOS, OSWALDO IVAN"),
    ("BALDETTI ELIAS DE PAZ", "BALDETTI ELIAS"),
    ("BALDIZON MENDEZ, MANUEL", "BALDIZON MENDEZ, MANUEL ANTONIO"),
    ("BALDIZON MENDEZ, SALVADOR", "BALDIZON MENDEZ, SALVADOR FRANCISCO"),
    ("BALLSELS TUT", "BALSELLS TUT"),
    ("BALSELL TUT", "BALSELLS TUT"),
    ("BAUR PAIZ", "BAUER PAIZ"),
    ("BAUSTISTA GODINEZ", "BAUTISTA GODINEZ"),
    ("BERGANZA BOJORGUEZ", "BERGANZA BOJORQUEZ"),
    ("BERGANZA BOJORQUEZ, FERDY LEONEL", "BERGANZA BOJORQUEZ"),
    ("BERGANZA BOJORQUEZ, FERDY NOEL", "BERGANZA BOJORQUEZ"),
    ("BLACO LAPOLA", "BLANCO LAPOLA"),
    ("BOUSINNOT NUILA", "BOUSSINOT NUILA"),
    ("CABRERAWESTERHEYDE", "CABRERA WESTERHEYDE"),
    ("CASTELLANOS CALL", "CASTELLANOS CAAL"),
    ("CHAVEZ GARCCIA", "CHAVEZ GARCIA"),
    ("CHAY LAINEZ", "CHAY LAYNEZ"),
    ("CHINCHILLA GUZMAN, OSCAR ARTURO", "CHINCHILLA GUZMAN"),
    ("CHINCHILLA GUZMAN, OSCAR STUARDO", "CHINCHILLA GUZMAN"),
    ("CIFUENTES BARRAGAN, GUILLERMO ALBERTO", "CIFUENTES BARRAGAN"),
    ("COJTY CHIROY", "COJTI CHIROY"),
    ("CONDE ORELLANA", "CONDE ORELLANA"),
    ("CONDE ORALLANA", "CONDE ORELLANA"),
    ("CONDE ORELANA", "CONDE ORELLANA"),
    ("CONDON ORELLANA", "CORDON ORELLANA"),
    ("CONTRERAS COLINDES", "CONTRERAS COLINDRES"),
    ("CREPO VILLEGAS", "CRESPO VILLEGAS"),
    ("DE LA CRUZ GELPECKE", "DE LA CRUZ GELPCKE"),
    ("DE LA TARRE GIMENO", "DE LA TORRE GIMENO"),
    ("DE LEON CORADO", "LEON CORADO"),
    # --- Block 2 (lines 400–421) ---
    ("DUARTE SAENZ", "DUARTE SAENZ DE TEJADA"),
    ("ESCOBAR, RONNIE", "ESCOBAR, RONNIE DANILO"),
    ("ESCOBAR, VICTOR", "ESCOBAR, VICTOR MANUEL"),
    ("FELIX LOEZ", "FELIX LOPEZ"),
    ("FELIZ LOPEZ", "FELIX LOPEZ"),
    ("FERNADEZ ESCOBAR", "FERNANDEZ ESCOBAR"),
    ("FERNDANDEZ ESCOBAR", "FERNANDEZ ESCOBAR"),
    ("GALDAMEZ                 JUAREZ", "GALDAMEZ JUAREZ"),
    ("GARCIA GRACIA", "GARCIA GARCIA"),
    ("GONZALEZ AGULAR", "GONZALEZ AGUILAR"),
    ("GONZALEZ GRCIA", "GONZALEZ GARCIA"),
    ("GONZALEZ VELAZQUEZ", "GONZALEZ VELASQUEZ"),
    ("HENGSTENBERG STUBSS", "HENGSTENBERG STUBBS"),
    ("HENSTENBERG STUBBS", "HENGSTENBERG STUBBS"),
    ("HEREIDA CASTRO", "HEREDIA CASTRO"),
    ("KESTLER VESLASQUEZ", "KESTLER VELASQUEZ"),
    ("ARCEO CARILLO", "ARCEO CARRILLO"),
    ("ARREGA MEZA DE CARDONA", "ARREAGA MEZA DE CARDONA"),
    ("ARREAGA MEZA", "ARREAGA MEZA DE CARDONA"),
    ("BACK ALVARADO", "BACK ALVARADO DE MONTE"),
    ("BAC ALVARADO DE MONTE", "BACK ALVARADO DE MONTE"),
    ("BAC ALVARADO", "BACK ALVARADO DE MONTE"),
    ("BARILLAS DE DUARTE", "BARILLAS CARIAS DE DUARTE"),
    ("BARREDA ROBLES", "BARRERA ROBLES"),
    ("BARRAEDA TARACENA", "BARREDA TARACENA"),
    ("BARREDA VILLANUEVA", "BARRERA VILLANUEVA"),
    ("CAMEY DE NOACK", "CAMEY SILVA DE NOACK"),
    ("CAMEY SILVA DE NOAK", "CAMEY SILVA DE NOACK"),
    ("CARDONA ARREAGA", "CARDONA ARREAGA DE POJOY"),
    # --- Block 3 (lines 430–491) ---
    ("CARILLO DE LEON", "CARRILLO DE LEON"),
    ("ESTRADA MASILLA", "ESTRADA MANSILLA"),
    ("FIGUERA RESEN DE CORO", "FIGUEROA RESEN DE CORO"),
    ("FIGUEROA RESEN", "FIGUEROA RESEN DE CORO"),
    ("GUERRERO DE LA CRUZ.", "GUERRERO DE LA CRUZ"),
    ("HERNANDEZ PEREZ", "HERNANDEZ PEREZ DE MORALES"),
    ("LAINIFIESTA CACERES", "LAINFIESTA CACERES"),
    ("LINARES BALTRANENA", "LINARES BELTRANENA"),
    ("LINARES BELTRANETA", "LINARES BELTRANENA"),
    ("ALONZO MAZARIEGOS", "MAZARIEGOS, ALONZO"),
    ("LINARES GARCIAS", "LINARES GARCIA"),
    ("LOPEZ CHACON DE GIL", "LOPEZ CHACON"),
    ("LUX COTI", "LUX GARCIA"),
    ("LUX GARCIA DE COTI", "LUX GARCIA"),
    ("MARROQUIN DE PALOMO", "MARROQUIN GODOY DE PALOMO"),
    ("MARTINEZ HENANDEZ", "MARTINEZ HERNANDEZ"),
    ("MARTINEZ HERNANDEZ,", "MARTINEZ HERNANDEZ"),
    ("MENDEZ HEBRUGER", "MENDEZ HERBRUGER"),
    ("MENDEZ HERBURGER", "MENDEZ HERBRUGER"),
    ("MENDEZ HERGRUGER", "MENDEZ HERBRUGER"),
    ("MIRANDO TREJO", "MIRANDA TREJO"),
    ("MONSANTO PABLO", "MONSANTO"),
    ("MONSANTO, PABLO", "MONSANTO"),
    ("MONTENEGRO COTOM", "MONTENEGRO COTTOM"),
    ("MONTENEGRO COTON", "MONTENEGRO COTTOM"),
    ("MONTENEGRO COTTON", "MONTENEGRO COTTOM"),
    ("MONTENEGRO COTTONE", "MONTENEGRO COTTOM"),
    ("MONTENGRO COTTOM", "MONTENEGRO COTTOM"),
    ("MONTENGRO COTTON", "MONTENEGRO COTTOM"),
    ("MOTTA KOLEFF", "MOTTA KOLLEFF"),
    ("OLIVA MURALES", "OLIVA MURALLES"),
    ("OTOZOY COLAJ", "OTZOY COLAJ"),
    ("PANIGUA RODRIGUEZ", "PANIAGUA RODRIGUEZ"),
    ("PEREZ VALLES DE CASTELLANOS", "PEREZ VALLES"),
    ("POC AC", "POP AC"),
    ("PORRAS C.A.STILLO", "PORRAS CASTILLO"),
    ("PRECIADO NARARIJO", "PRECIADO NAVARIJO"),
    ("PRESIDENDA RIVERA ZALDANA", "PRESIDENTA RIVERA ZALDANA"),
    ("PRESIDENTE ACCIDENTAL ZACRISSON CASTILLO", "PRESIDENTE ACCIDENTAL ZACHRISSON CASTILLO"),
    ("PRESIDENTE AJELOS CAMBARA", "PRESIDENTE ALEJOS CAMBARA"),
    ("PRESIDENTE MENDEZ HERBURGER", "PRESIDENTE MENDEZ HERBRUGER"),
    ("PRESIDENTE MORALEZ CHAVEZ", "PRESIDENTE MORALES CHAVEZ"),
    ("PRESIDENTE MONTT", "PRESIDENTE RIOS MONTT"),
    ("PRESIDENTE RIOS MONNT", "PRESIDENTE RIOS MONTT"),
    ("PRESIDENTE RIOS MONT", "PRESIDENTE RIOS MONTT"),
    ("PRESIDENTE RIOS MOTT", "PRESIDENTE RIOS MONTT"),
    ("PRESIDENTE, RIOS MONTT", "PRESIDENTE RIOS MONTT"),
    ("PRESISDENTE RIOS MONTT", "PRESIDENTE RIOS MONTT"),
    ("RESIDENTE RIOS MONTT", "PRESIDENTE RIOS MONTT"),
    ("EL PRESIDENTE RIOS MONTT", "PRESIDENTE RIOS MONTT"),
    ("PRESIDENTERODRIGUEZ REYES", "PRESIDENTE RODRIGUEZ REYES"),
    ("RAMIREZ HERNADEZ", "RAMIREZ HERNANDEZ"),
    ("RAMIREZ RETANA DE NAJERA", "RAMIREZ RETANA"),
    ("RAMIREZ RENTANA", "RAMIREZ RETANA"),
    ("REINHARADT MOSQUERA", "REINHARDT MOSQUERA"),
    ("REYES LEE, EDGAR", "REYES LEE, EDGAR RAUL"),
    ("REYES LEE EDGAR RAUL", "REYES LEE, EDGAR RAUL"),
    ("REYES LEE FIDEL", "REYES LEE, FIDEL"),
    ("RIOS SOSA, ZURY", "RIOS SOSA"),
    ("RIOZ MUNOZ", "RIOS MUNOZ"),
    ("RIVERA SAGASTUME, EDGAR ABRAHAM", "RIVERA SAGASTUME"),
    ("RIVERA SAGATUME", "RIVERA SAGASTUME"),
    ("ROS ACEVEDO, CHRISTIAN MICHAEL", "ROS ACEVEDO"),
    ("SALAZAR DE LEON, ADOLFO ALEJANDRO", "SALAZAR DE LEON"),
    ("SALAZAR DE LEON, RODOLFO ALEJANDRO", "SALAZAR DE LEON"),
    ("SAMAYOA BARRIOS, NERY ROLANDO", "SAMAYOA BARRIOS"),
    ("SAMAYORA BARRIOS", "SAMAYOA BARRIOS"),
    ("SAMAYORA PEREIRA", "SAMAYOA PEREIRA"),
    ("SAMINES CHILE", "SAMINES CHALI"),
    ("SANABRA ARIAS", "SANABRIA ARIAS"),
    ("SANCHEZ ABASCAL DE RAMOS", "SANCHEZ ABASCAL"),
    ("SANCHEZ GUMAN", "SANCHEZ GUZMAN"),
    ("SANDINO REYES", "SANDINO REYES ROSALES"),
    ("SANTACRUZ CU", "SANTA CRUZ CU"),
    ("SCHELL AGUILAR", "SCHEEL AGUILAR"),
    ("SOLIC ICO", "SOLIS ICO"),
    ("TABUSCH PASCUAL DE SANCHEZ", "TABUSH PASCUAL DE SANCHEZ"),
    ("TAMBRIIZ Y TAMBRIZ", "TAMBRIZ Y TAMBRIZ"),
    ("VELASQUEZ PEREZ, GERMAN EDUARDO", "VELASQUEZ PEREZ, GERMAN ESTUARDO"),
    ("VELASQUEZ PEREZ, GERMAN", "VELASQUEZ PEREZ, GERMAN ESTUARDO"),
    ("VELASQUEZ, ALVARO ADOLFO", "VELASQUEZ, ALVARO"),
    ("VILLAGAN ALVAREZ", "VILLAGRAN ALVAREZ"),
    ("VILLAGRAN ANTON DE PANTOJA", "VILLAGRAN ANTON"),
    ("VILLAGRAN ARDON", "VILLAGRAN ANTON"),
    ("VILLATE VILLATORIO", "VILLATE VILLATORO"),
    ("VILLATORO MONTENEGRO", "VILLATORO MONTERROSO"),
    ("WHOLERS MONROY", "WOHLERS MONROY"),
    (
        "ZACHRISSON CASTILLO, PRESIDENTE DE LA COMISION DE LEGISLACION Y PUNTOS CONSTITUCIONALES, EN FUNCIONES DE PRESIDENTE",
        "ZACHRISSON CASTILLO",
    ),
    ("ZACRHISSON CASTILLO", "ZACHRISSON CASTILLO"),
    ("ZEA", "ZEA SIERRA"),
    ("ACCIDENTALMAZARIEGOS", "MAZARIEGOS"),
    ("RIVERA ESTEVEZ , JUAN CARLOS", "RIVERA ESTEVEZ, JUAN CARLOS"),
    ("ALEJOS LORANZANA", "ALEJOS LORENZANA"),
    ("PINTO RAMIREZ", "PINTO MARTINEZ"),
    (
        "ALVAREZ MORALES Y LA R. ALVAREZ MORALES Y LA R. MONTENEGRO COTTOM EL R. PRESIDENTE RABBE TEJADA, LUIS ARMANDO",
        "PRESIDENTE RABBE TEJADA, LUIS ARMANDO",
    ),
    ("GARCIABUENAFE", "GARCIA BUENAFE"),
    ("BARCIA BUENAFE", "GARCIA BUENAFE"),
    ("BARILLAS CARIAS", "BARILLAS CARIAS DE DUARTE"),
    ("BARRILLAS DE DUARTE", "BARILLAS CARIAS DE DUARTE"),
    ("BARILLAS HERREA", "BARILLAS HERRERA"),
    ("BARILLLAS HERRERA", "BARILLAS HERRERA"),
    ("BARRILLAS HERRERA", "BARILLAS HERRERA"),
    ("CASTELLON FUENTES", "CASTANON FUENTES"),
    ("CERDAS ARGUETA", "CARDENAS ARGUETA"),
    ("CHACON LOPEZ", "LOPEZ CHACON"),
    ("CHANG LAYNEZ", "CHAY LAYNEZ"),
    ("CHINCHIILLA GUZMAN", "CHINCHILLA GUZMAN"),
    ("CHINCHILLA VEGA", "CHINCHILLA GUZMAN"),
    ("CIUDADANO VALLE TORRES", "VALLE TORRES"),
    ("CRUZ GONZALEZ", "GONZALEZ NAVARRO"),
    ("CIFUENTES DE LEON", "CIFUENTES VELASQUEZ"),
    ("CHUTA DE LARA", "MEJIA CHUTA DE LARA"),
    ("ALVARO TRUJILLO", "TRUJILLO BALDIZON"),
    ("BARRIOS SAMAYOA", "SAMAYOA BARRIOS"),
    ("BORIS ESPANA", "ESPANA CACERES"),
    ("GUDY RIVERA", "RIVERA ESTRADA"),
    ("EL PRESIDENTE ALEJOS CAMBARA", "ALEJOS CAMBARA"),
    ("CARDONA CHIC", "CHIC CARDONA"),
    ("CARDONA ESTRADA", "RIVERA ESTRADA"),
    ("ZALDANA RIVERA", "RIVERA ZALDANA"),
    ("DE ANGEL MADRID DE FRADE", "ANGEL MADRID DE FRADE"),
    ("EL SENOR DE LEON DUQUE", "DE LEON DUQUE"),
    ("TEBALAN DE LEON", "TEVALAN DE LEON"),
    ("SECRETARO TEVALAN DE LEON", "TEVALAN DE LEON"),
    ("LEON RUIZ", "DE LEON RUIZ"),
    ("DE LEON DE LEON", "DE LEON DE LEON DE PEREZ"),
    ("DUARTE DE SAMAYOA", "DUARTE AVILA"),
    ("DUARTE", "DUARTE SOTO"),
    ("DURAN BARQUIN", "BARQUIN DURAN"),
    ("ESCOBAR FERNANDEZ", "FERNANDEZ ESCOBAR"),
    ("ESPINO ROJAS", "ROJAS ESPINO"),
    ("FELIX ROLANDO WALTER ROLANDO", "FELIX LOPEZ"),
    ("FLORA DE RAMOS", "ESCOBAR GORDILLO DE RAMOS"),
    ("FRANCISCO TAMBRIZ Y TAMBRIZ", "TAMBRIZ Y TAMBRIZ"),
    ("GABRIEL HEREDIA", "HEREDIA CASTRO"),
    ("GACIA RODAS", "GARCIA RODAS"),
    ("GALIM MORALES", "MORALES BARRIOS"),
    ("GARCIA BUENFE", "GARCIA BUENAFE"),
    ("GOMEZ RAYMUNDO", "GONZALEZ GOMEZ"),
    ("SANTIAGO NAJERA", "NAJERA SAGASTUME"),
    ("NAJERA PEREZ", "NAJERA SAGASTUME"),
    ("HERNADEZ RUBIO", "HERNANDEZ RUBIO"),
    ("HERNANDEZ RUIBO", "HERNANDEZ RUBIO"),
    ("HERNANEZ RUBIO", "HERNANDEZ RUBIO"),
    ("HERNANDEZ MARTINEZ", "MARTINEZ HERNANDEZ"),
    ("MARTINEZ HERNANEZ", "MARTINEZ HERNANDEZ"),
    ("SECRETARO PEREZ MARTINEZ", "PEREZ MARTINEZ"),
    ("MARTINEZ HERRERA, EDWIN", "MARTINEZ HERRERA, EDWIN ARMANDO"),
    ("MARTINEZ HERRERA, JOEL", "MARTINEZ HERRERA, JOEL RUBEN"),
    ("MARTA ODILIA CUELLAR GIRON DE MARTINEZ", "CUELLAR GIRON DE MARTINEZ"),
    ("GUTIERREZ VELASQUEZ", "GUTIERREZ RAGUAY"),
    ("HERERRA QUEZADA", "HERRERA QUEZADA"),
    ("LECSAN MERIDA", "MERIDA HERRERA"),
    ("LUX", "MALDONADO LUX"),
    ("MACK HERNANDEZ", "HERNANDEZ MACK"),
    ("MALDONADO", "MALDONADO AGUIRRE"),
    ("MANSILLA ESTRADA", "ESTRADA MANSILLA"),
    ("MARIANO RAYO", "RAYO MUNOZ"),
    ("MARTINEZ HERNANDEZ, KARLA", "MARTINEZ HERNANDEZ, KARLA ANDREA"),
    ("MARTINEZ HERNANDEZ, ERICK", "MARTINEZ HERNANDEZ, ERICK GEOVANY"),
    ("MENDER URIZAR", "MENDEZ URIZAR"),
    ("MERIDA GUZMAN", "GUZMAN MERIDA"),
    (
        "RICARDO ROSALES ROMAN, DIPUTADO DE LA COALICION DIA-URNG-ALIANZA NUEVA NACION",
        "ROSALES ROMAN",
    ),
    ("MONETENGRO COTTON", "MONTENEGRO COTTOM"),
    ("NINETH MONTENEGRO", "MONTENEGRO COTTOM"),
    ("MONTEGRO FLORES", "MONTENEGRO FLORES"),
    ("MORALES AVILA", "ROBLES AVILA"),
    ("MORALES HURTADO", "MORAN HURTADO"),
    ("MORALES Y MORALES", "MORALES MORALES"),
    ("MORALEZ CHAVEZ", "MORALES CHAVEZ"),
    ("MURALLES OLIVA", "OLIVA MURALLES"),
    ("PEREZ ARTINEZ", "PEREZ MARTINEZ"),
    ("PEREZ RAMIREZ", "PEREZ MARTINEZ"),
    ("PONCE DE SAMAYOA", "PONCE BROCKE DE SAMAYOA"),
    ("QUEJ CHEN, ERIC HAROLDO", "QUEJ CHEN, HAROLDO ERIC"),
    ("QUEJ CHEN", "QUEJ CHEN, EDUARDO GENIS"),
    ("RABBE TEJADA", "RABBE TEJADA, LUIS ARMANDO"),
    ("RANCANCOJ ALONZO", "RACANCOJ ALONZO"),
    ("REYES LEE, AUGUSTO CESAR SANDINO", "REYES ROSALES"),
    ("SANDINO REYES ROSALES", "REYES ROSALES"),
    ("RODRIGUEZ REYES, ALLAN ESTUARDO", "RODRIGUEZ REYES"),
    ("REYES RODRIGUEZ", "RODRIGUEZ REYES"),
    ("RODIGUEZ REYES, ALLAN ESTUARDO", "RODRIGUEZ REYES"),
    ("RIVERA GARCIA", "RIVERA NAJERA"),
    ("RODAS LOPEZ", "LOPEZ RODAS"),
    ("RODAS MENDEZ", "RODAS MENDEZ, NERY MAMFREDO"),
    ("RODRIGUEZ", "RODRIGUEZ, EDGAR ALFREDO"),
    ("RODRIGUEZ, EDGAR", "RODRIGUEZ, EDGAR ALFREDO"),
    ("ROSALES PAZ", "PAZ ROSALES"),
    ("ROSASLES MARROQUIN", "ROSALES MARROQUIN"),
    ("ROXANA BALDETTI", "BALDETTI ELIAS"),
    ("SALAZAR", "SALAZAR MIRON"),
    ("SAMAYOA RODRIGUEZ", "SAMAYOA BARRIOS"),
    ("SANDOVAL", "SANDOVAL MARTINEZ"),
    ("SOLANO", "SOLANO, JOSE CARLO"),
    ("SOLORZANO RODRIGUEZ", "SOLORZANO RIVERA"),
    ("VELAQUEZ BAMACA", "VELASQUEZ BAMACA"),
    ("VILLALTORO SAN JOSE", "VILLATORO SAN JOSE"),
    ("WELLMANN AROLDO", "WELLMANN CHRIST"),
    ("WILHELM", "WELLMANN CHRIST"),
    ("ZACRISSON CASTILLO", "ZACHRISSON CASTILLO"),
    ("VELAZQUEZ", "VELASQUEZ"),
    ("LINARES-BELTRANENA", "LINARES BELTRANENA"),
    ("TARACENA DIAZ-SOL", "TARACENA DIAZ SOL"),
    ("SAENZ DE TEJADA", "DUARTE SAENZ DE TEJADA"),
    ("SOLORZADO QUEVEDO", "SOLORZANO QUEVEDO"),
    ("AZMITIA HERNANDEZ", "HERNANDEZ AZMITIA"),
    ("VELASQUEZ REYES", "VELASQUEZ, ALVARO ADOLFO"),
    ("RODRIGUEZ PEREZ", "RODRIGUEZ REYES, ALLAN ESTUARDO"),
    ("MENDEZ", "BALDIZON MENDEZ, MANUEL ANTONIO"),
    ("ESCOBAR DE RAMOS", "ESCOBAR GORDILLO DE RAMOS"),
    ("ARISTIDES CRESPO", "CRESPO VILLEGAS"),
    ("RODAS GARCIA", "GARCIA RODAS"),
    ("VELASQUEZ VELASQUEZ", "VASQUEZ VELASQUEZ"),
    ("PRESIDENTA RIVERA ZALDANA", "RIVERA ZALDANA"),
    ("RODRIGUEZ REYES", "RODRIGUEZ REYES, ALLAN ESTUARDO"),
    ("REYES RODRIGUEZ", "RODRIGUEZ REYES, ALLAN ESTUARDO"),
    ("HERNANDEZ RUBIO DE COMISION PERMANENTE", "HERNANDEZ RUBIO"),
    ("CUELLAR GIRON", "CUELLAR GIRON DE MARTINEZ"),
    ("AREVALO BARRIOS", "AREVALO BARRIOS, OSWALDO IVAN"),
    ("BARRIOS", "BARRIOS GALINDO"),
    ("VELASQUEZ", "VELASQUEZ, ALVARO ADOLFO"),
    ("VELASQUEZ ALVARO", "VELASQUEZ, ALVARO ADOLFO"),
    ("VELASQUEZ, ALVARO", "VELASQUEZ, ALVARO ADOLFO"),
    ("RODRIGUEZ AZPURU-ORDONEZ", "RODRIGUEZ AZPURU ORDONEZ"),
    ("RODRIGUEZ-AZPURU", "RODRIGUEZ AZPURU ORDONEZ"),
    ("RODRIGUEZ-AZPURU ORDONES", "RODRIGUEZ AZPURU ORDONEZ"),
    ("RODRIGUEZ-AZPURU ORDONEZ", "RODRIGUEZ AZPURU ORDONEZ"),
    ("SOTO AGUIRRE", "EL SENOR MINISTRO DE GOBERNACION, LICENCIADO SOTO AGUIRRE"),
    ("ZAPATA SAGASTUME", "EL SENOR SUPERINTENDENTE DE ADMINISTRACION TRIBUTARIA, LICENCIADO ZAPATA SAGASTUME"),
]

# Build lookup dict (later entries override earlier ones for same key)
GT_CORRECTIONS_DICT: dict[str, str] = {wrong: canon for wrong, canon in _SIMPLE_LIST}


# ── Conditional corrections ────────────────────────────────────────────────────

def _apply_conditional(
    nm: str,
    speaker_raw: str,
    legislature: str,
    d: date,
    filename: str,
) -> str:
    """
    Apply context-dependent corrections (R lines 423–681).
    Takes already-normalized nm_fuse and additional context fields.
    """

    # Cifuentes Barragán: gender disambiguation via speaker prefix (lines 509–511)
    if nm == "CIFUENTES BARRAGAN":
        if speaker_raw == "EL R. CIFUENTES BARRAGÁN":
            return "CIFUENTES BARRAGAN, GUILLERMO ALBERTO"
        if speaker_raw == "LA R. CIFUENTES BARRAGÁN":
            return "CIFUENTES BARRAGAN, GLADIS CAROLINA"
        return "CIFUENTES BARRAGAN, GUILLERMO ALBERTO"

    # Cardona Arreaga: leg VIII means the individual deputy, not the compound (line 423)
    if speaker_raw == "EL R. CARDONA ARREAGA" and legislature == "VIII":
        return "CARDONA ARREAGA"

    # González García in leg VIII → González Alvarado (line 425)
    if speaker_raw == "EL R. GONZÁLEZ GARCÍA" and legislature == "VIII":
        return "GONZALEZ ALVARADO"

    # Mazariegos: leg VI female → Aquino Mazariegos (line 561)
    if legislature == "VI" and speaker_raw in (
        "LA R. MAZARIEGOS",
        "LA R. SECRETARIA MAZARIEGOS",
        "LA R. SECRETARIA ACCIDENTAL MAZARIEGOS",
        "LA R. SECRETARIA ACCIDENTALMAZARIEGOS",
    ):
        return "AQUINO MAZARIEGOS"
    if nm == "MAZARIEGOS":
        return "MAZARIEGOS LOPEZ"
    if nm == "MAZARIEGOS, ALONZO":
        return "PRESIDENTE DE LA COMISION LIQUIDADORA DEL BANCO NACIONAL DE LA VIVIENDA, ALONZO MAZARIEGOS"

    # Martínez Hernández gender split (lines 558–559)
    if speaker_raw in (
        "LA R. MARTÍNEZ HERNÁNDEZ",
        "LA R. MARTÍNEZ HENÁNDEZ",
        "LA R. SECRETARIA MARTÍNEZ HERNÁNDEZ",
        "LA R. SECRETARIA MARTÍNEZ HERNÁNEZ",
        "LA R. MARTINEZ HERNANDEZ",
    ):
        return "MARTINEZ HERNANDEZ, KARLA ANDREA"
    if speaker_raw in (
        "EL R. MARTÍNEZ HERNÁNDEZ",
        "EL R. HERNÁNDEZ MARTÍNEZ",
        "EL R. MARTÍNEZ HERNÁNDEZ,",
    ):
        return "MARTINEZ HERNANDEZ, ERICK GEOVANY"

    # Rivera Estevez (lines 585–587)
    if speaker_raw in (
        "EL R. SECRETARIO RIVERA ESTEVEZ",
        "EL R. SECRETARIO ACCIDENTAL RIVERA ESTEVEZ",
    ):
        return "RIVERA ESTEVEZ, JUAN CARLOS"
    if nm == "RIVERA ESTEVEZ":
        if d == date(2008, 9, 3):
            return "RIVERA ESTEVEZ, EDGAR ABRAHAM"
        return "RIVERA ESTEVEZ, JUAN CARLOS"

    # García Gudiel: specific file + specific speaker (line 677)
    if (
        filename == "62303-diario-final-ss-01-2008__14-01-08.pdf"
        and speaker_raw == "EL R. SECRETARIO GARCIA Y GARCIA"
    ):
        return "GARCIA GUDIEL"

    # Chávez Pérez in legislature VII (line 679)
    if legislature == "VII" and speaker_raw == "EL R. CHAVEZ GARCIA":
        return "CHAVEZ PEREZ"

    # Baldizon Mendez date split (lines 617–618)
    if nm == "BALDIZON MENDEZ":
        return (
            "BALDIZON MENDEZ, MANUEL ANTONIO"
            if d < date(2008, 1, 14)
            else "BALDIZON MENDEZ, SALVADOR FRANCISCO"
        )

    # De Leon Torres date split (lines 619–621 — R has a logic bug; applied chronologically)
    if nm == "DE LEON TORRES":
        if d >= date(2025, 9, 30):
            return "DE LEON TORRES, NADIA LORENA"
        if d >= date(2024, 10, 3):
            return "DE LEON TORRES, NADIA LORENA"
        if d >= date(2024, 2, 29):
            return "DE LEON TORRES, LOURDES TERESITA"
        return "DE LEON TORRES, LOURDES TERESITA"

    # Escobar date split (lines 622–623)
    if nm == "ESCOBAR":
        return (
            "ESCOBAR, VICTOR MANUEL"
            if d < date(2008, 1, 14)
            else "ESCOBAR, RONNIE DANILO"
        )

    # Martínez Herrera date split (lines 624–626)
    if nm == "MARTINEZ HERRERA":
        if d >= date(2016, 1, 14):
            return "MARTINEZ HERRERA, JOEL RUBEN"
        if d < date(2004, 1, 14):
            return "MARTINEZ HERRERA, EDWIN ARMANDO"
        return "MARTINEZ HERRERA, JOEL RUBEN"

    # Reyes Lee date split (lines 627–628, 647)
    if nm == "REYES LEE":
        if d == date(2019, 1, 17):
            return "REYES LEE, EDGAR RAUL"
        if d < date(2016, 1, 21):
            return "REYES LEE, FIDEL"
        return "REYES LEE, EDGAR RAUL"

    # Cruz Clavería date split (lines 630–631)
    if nm == "CRUZ CLAVERIA":
        return (
            "CRUZ CLAVERIA, JOSE LEOPOLDO"
            if d < date(2010, 1, 26)
            else "CRUZ CLAVERIA, VICTOR MANUEL"
        )

    # Fion Morales date split (lines 632–633)
    if nm == "FION MORALES":
        return (
            "FION MORALES, CARLOS RAFAEL"
            if d < date(2020, 1, 14)
            else "FION MORALES, CESAR AUGUSTO"
        )

    # García García date split (lines 634–635)
    if nm == "GARCIA GARCIA":
        return (
            "GARCIA GARCIA, JOB RAMIRO"
            if d < date(2008, 1, 14)
            else "GARCIA GARCIA, CORNELIO GONZALO"
        )

    # González Alvarado date split (lines 644–645)
    if nm == "GONZALEZ ALVARADO":
        return (
            "GONZALEZ ALVARADO, EUGENIO MOISES"
            if d < date(2020, 1, 14)
            else "GONZALEZ ALVARADO, DIEGO ISRAEL"
        )

    # Recinos Sandoval (line 646)
    if nm == "RECINOS SANDOVAL" and d < date(2008, 1, 14):
        return "RECINOS SANDOVAL WILLIAM"

    # Tzul Tzul date split (lines 649–650)
    if nm == "TZUL TZUL":
        return (
            "TZUL TZUL, GERONIMO BASILIO"
            if d < date(2004, 1, 14)
            else "TZUL TZUL, JULIO FELIPE"
        )

    # Velásquez Pérez date/specific-date split (lines 651–656)
    if nm == "VELASQUEZ PEREZ":
        if d < date(2008, 1, 14):
            return "VELASQUEZ PEREZ, CARLOS EDUARDO"
        if d > date(2024, 1, 14):
            return "VELASQUEZ PEREZ, MARIO"
        if d == date(2017, 9, 26):
            return "VELASQUEZ PEREZ, GERMAN ESTUARDO"
        if d in (date(2016, 1, 28), date(2016, 2, 2), date(2016, 4, 7)):
            return "VELASQUEZ PEREZ, MARIO"
        if d in (
            date(2016, 6, 9), date(2017, 4, 27), date(2018, 3, 22),
            date(2018, 2, 8), date(2018, 2, 20), date(2016, 3, 29),
        ):
            return "VELASQUEZ PEREZ, GERMAN ESTUARDO"
        if d == date(2016, 1, 21):
            return "VELASQUEZ, ALVARO ADOLFO"
        return "VELASQUEZ PEREZ, GERMAN ESTUARDO"

    # Zamora Ruiz date split (lines 657–658)
    if nm == "ZAMORA RUIZ":
        return (
            "ZAMORA RUIZ, EDGAR ROLANDO"
            if d < date(2020, 1, 14)
            else "ZAMORA RUIZ, LAZARO VINICIO"
        )

    # García y García date split (lines 669–670)
    if nm == "GARCIA Y GARCIA":
        return (
            "GARCIA Y GARCIA, JOB RAMIRO"
            if d < date(2020, 1, 14)
            else "GARCIA GARCIA, CORNELIO GONZALO"
        )

    # Oliva Muralles (lines 671–672; both branches same result)
    if nm == "OLIVA MURALLES":
        return "OLIVA MURALLES, MACARIO EFRAIN"

    return nm


def _apply_final_strips(nm: str) -> str:
    """
    Final regex-based cleanups (R lines 608–616).
    Must run AFTER conditional corrections.
    """
    # Protect "PRESIDENTE DE" from the next strip
    nm = re.sub(r'^PRESIDENTE DE', '\x00PRESIDENTE DE', nm)
    nm = re.sub(r'^PRESIDENTE ', '', nm)
    nm = re.sub(r'^DIPUTADA ', '', nm)
    nm = re.sub(r'^DIPUTADO ', '', nm)
    nm = nm.replace('\x00', '')  # restore
    if nm == '':
        nm = 'PRESIDENTE'
    return nm


_POST_CORRECTIONS = {
    "AREVALO BARRIOS": "AREVALO BARRIOS, OSWALDO IVAN",
    "BARRIOS": "BARRIOS GALINDO",
    "HERNANDEZ RUBIO DE COMISION PERMANENTE": "HERNANDEZ RUBIO",
    "CUELLAR GIRON": "CUELLAR GIRON DE MARTINEZ",
}


def correct_nm_fuse(
    nm: str,
    speaker_raw: str = '',
    legislature: str = '',
    d: date | None = None,
    filename: str = '',
) -> str:
    """
    Apply the complete GT name correction pipeline (equivalent to R lines 373–681).

    Args:
        nm:           Already-normalized nm_fuse (output of normalize_speaker).
        speaker_raw:  Original raw speaker string (with accents) for disambiguation.
        legislature:  Legislature code (IV–X) for context-dependent corrections.
        d:            Session date for date-sensitive splits.
        filename:     PDF basename for file-specific corrections.

    Returns:
        Corrected canonical nm_fuse string.
    """
    if d is None:
        d = date.min

    # 1. Simple dict lookup
    nm = GT_CORRECTIONS_DICT.get(nm, nm)

    # 2. Conditional (context-dependent) corrections
    nm = _apply_conditional(nm, speaker_raw, legislature, d, filename)

    # 3. Final prefix strips + empty → PRESIDENTE
    nm = _apply_final_strips(nm)

    # 4. Post-strip residual corrections
    nm = _POST_CORRECTIONS.get(nm, nm)

    return nm
