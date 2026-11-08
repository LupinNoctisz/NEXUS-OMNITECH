"""Separa um texto de identificação (etiqueta, caixa, nota da OS) em fabricante, modelo e serial.

Princípios:
* nunca inventa: só devolve o que está no texto; o que não puder ser atribuído com segurança
  fica vazio e vai para ``alternatives``/``warnings``;
* cada campo diz de onde veio (``sources``): ``rótulo`` (o texto dizia "Modelo: ..."),
  ``fabricante conhecido`` (nome encontrado na lista) ou ``texto restante`` (palpite);
* o resultado é uma SUGESTÃO para o técnico conferir, nunca um dado confirmado.
"""

from __future__ import annotations

import re
from typing import Any

# nome canônico -> variações aceitas (comparação sem diferenciar maiúsculas, por palavra inteira)
_VENDORS: dict[str, tuple[str, ...]] = {
    "Dell": ("dell", "dell inc", "dell technologies"),
    "HP": ("hp", "hp inc", "hewlett-packard", "hewlett packard", "hpe"),
    "Lenovo": ("lenovo", "ibm"),
    "ASUS": ("asus", "asustek", "asustek computer", "republic of gamers", "rog"),
    "Acer": ("acer", "packard bell"),
    "Samsung": ("samsung",),
    "LG": ("lg", "lg electronics"),
    "Apple": ("apple", "macbook", "iphone", "ipad", "imac"),
    "Positivo": ("positivo", "positivo bgh"),
    "Multilaser": ("multilaser",),
    "Intel": ("intel", "intel corporation"),
    "AMD": ("amd", "advanced micro devices"),
    "NVIDIA": ("nvidia",),
    "Gigabyte": ("gigabyte", "gigabyte technology", "aorus"),
    "MSI": ("msi", "micro-star", "micro star"),
    "ASRock": ("asrock",),
    "Kingston": ("kingston",),
    "SanDisk": ("sandisk",),
    "Crucial": ("crucial", "micron"),
    "Seagate": ("seagate",),
    "Western Digital": ("western digital", "wd"),
    "Toshiba": ("toshiba",),
    "Sony": ("sony",),
    "Microsoft": ("microsoft", "xbox"),
    "Nintendo": ("nintendo",),
    "Motorola": ("motorola", "moto"),
    "Xiaomi": ("xiaomi", "redmi", "poco"),
    "Huawei": ("huawei",),
    "Corsair": ("corsair",),
    "Logitech": ("logitech",),
    "TP-Link": ("tp-link", "tplink"),
    "Cooler Master": ("cooler master", "coolermaster"),
    "EVGA": ("evga",),
    "Canon": ("canon",),
    "Epson": ("epson",),
    "Brother": ("brother",),
    "Realtek": ("realtek",),
}

_KIND_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mobile", ("celular", "smartphone", "iphone", "galaxy", "imei", "tablet", "ipad")),
    ("console", ("playstation", "ps4", "ps5", "xbox", "nintendo", "switch", "console", "videogame")),
    ("usb", ("pen drive", "pendrive", "flash drive", "hd externo", "ssd externo", "usb")),
    ("pc", ("notebook", "laptop", "desktop", "computador", "all-in-one", "all in one", "pc")),
)

_MODEL_LABEL = r"(?:modelo|model(?:\s*(?:name|no\.?|number))?|mod\.?|produto|product(?:\s*name)?|part\s*number|p/n)"
_VENDOR_LABEL = r"(?:fabricante|manufacturer|marca|brand|vendor|mfr)"
_SERIAL_LABEL = (r"(?:n[úu]mero\s+de\s+s[ée]rie|n[º°o]\.?\s*(?:de\s*)?s[ée]rie|serial\s*(?:number|no\.?|nr\.?)?|"
                 r"service\s*tag|svc\s*tag|s/n|n/s|sn)")
_IMEI_LABEL = r"imei\s*[12]?"
_SEP = r"\s*[:=#]\s*|\s+-\s+|\s+"

_SERIAL_VALUE = r"([A-Za-z0-9][A-Za-z0-9\-_./]{3,39})"
_RE_SERIAL = re.compile(rf"(?<![A-Za-z0-9])({_SERIAL_LABEL})(?:{_SEP}){_SERIAL_VALUE}", re.I)
_RE_IMEI = re.compile(rf"(?<![A-Za-z0-9])({_IMEI_LABEL})(?:{_SEP})(\d{{14,16}})(?!\d)", re.I)
_RE_MODEL = re.compile(rf"(?<![A-Za-z0-9])({_MODEL_LABEL})(?:\s*[:=#]\s*)(.+?)(?=\s{{2,}}|[;|\n]|$)", re.I)
_RE_VENDOR = re.compile(rf"(?<![A-Za-z0-9])({_VENDOR_LABEL})(?:\s*[:=#]\s*)(.+?)(?=\s{{2,}}|[;|\n]|$)", re.I)

# valores que o firmware/fabricante deixa de preenchimento e que NÃO são identificação real
_JUNK = re.compile(
    r"^(?:n/?a|none|null|unknown|desconhecido|default string|to be filled by o\.?e\.?m\.?|"
    r"system serial number|system product name|system manufacturer|not specified|not applicable|"
    r"o\.?e\.?m|oem|0+|1+|x+|\(standard[^)]*\)|\(generic[^)]*\)|generic|standard)$",
    re.I,
)


def clean_value(value: str | None) -> str | None:
    """Apara espaços e descarta textos de preenchimento (ex.: 'To be filled by O.E.M.', '0000')."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip().strip(".,;:|-").strip()
    if not text or _JUNK.match(text):
        return None
    return text


def _valid_serial(value: str) -> bool:
    value = value.strip(".-_/")
    return (len(value) >= 4 and any(ch.isdigit() for ch in value) and clean_value(value) is not None
            and len(set(value)) > 1)


def _find_vendor(text: str) -> tuple[str, int, int] | None:
    """Primeiro fabricante conhecido no texto (mais cedo vence; em empate, o nome mais longo)."""
    best: tuple[int, int, str, int] | None = None
    for canonical, aliases in _VENDORS.items():
        for alias in aliases:
            match = re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.I)
            if match and (best is None or (match.start(), -len(alias)) < (best[0], -best[1])):
                best = (match.start(), len(alias), canonical, match.end())
    if best is None:
        return None
    return best[2], best[0], best[3]


def _suggest_kind(text: str) -> str | None:
    lowered = text.lower()
    for kind, words in _KIND_WORDS:
        for word in words:
            if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", lowered):
                return kind
    return None


def identify(text: str) -> dict[str, Any]:
    """Devolve ``{kind, vendor, model, serial, sources, alternatives, warnings, unassigned}``."""
    original = (text or "").replace("\r", "\n")
    warnings: list[str] = []
    sources: dict[str, str] = {}
    alternatives: dict[str, list[str]] = {}
    work = original
    result: dict[str, Any] = {"kind": _suggest_kind(original), "vendor": None, "model": None, "serial": None}

    # --- serial (e IMEI) ---------------------------------------------------------------------
    serials: list[str] = []
    for match in _RE_SERIAL.finditer(original):
        value = match.group(2)
        if _valid_serial(value) and value not in serials:
            serials.append(value)
    imeis = list(dict.fromkeys(m.group(2) for m in _RE_IMEI.finditer(original)))
    if len(serials) == 1:
        result["serial"], sources["serial"] = serials[0], "rótulo"
    elif len(serials) > 1:
        alternatives["serial"] = serials
        warnings.append("Mais de um número de série no texto; escolha manualmente (veja as alternativas).")
    elif len(imeis) >= 1:
        if len(imeis) == 1:
            result["serial"], sources["serial"] = imeis[0], "rótulo (IMEI)"
            warnings.append("O serial foi preenchido com o IMEI; confira se o equipamento tem outro número de série.")
        else:
            alternatives["serial"] = imeis
            warnings.append("Mais de um IMEI no texto; escolha manualmente.")
    if len(serials) >= 1 and imeis:
        alternatives.setdefault("imei", imeis)
    if result["kind"] is None and imeis:
        result["kind"] = "mobile"
    # tira do texto restante só os trechos "rótulo + número" realmente aceitos como serial/IMEI
    work = _RE_IMEI.sub(lambda m: " " if m.group(2) in imeis else m.group(0), work)
    work = _RE_SERIAL.sub(lambda m: " " if m.group(2) in serials else m.group(0), work)

    # --- fabricante -----------------------------------------------------------------------------
    labeled_vendor = _RE_VENDOR.search(original)
    if labeled_vendor and clean_value(labeled_vendor.group(2)):
        raw = clean_value(labeled_vendor.group(2)) or ""
        known = _find_vendor(raw)
        result["vendor"] = known[0] if known and known[1] == 0 and len(raw) <= len(known[0]) + 12 else raw
        sources["vendor"] = "rótulo"
        work = work.replace(labeled_vendor.group(0), " ")
    else:
        found = _find_vendor(work)
        if found:
            result["vendor"], sources["vendor"] = found[0], "fabricante conhecido"

    # --- modelo ------------------------------------------------------------------------------------
    labeled_model = _RE_MODEL.search(original)
    if labeled_model and clean_value(labeled_model.group(2)):
        model = clean_value(labeled_model.group(2)) or ""
        if result["vendor"] and sources.get("vendor") == "fabricante conhecido":
            model = re.sub(rf"^(?:{'|'.join(re.escape(a) for a in _VENDORS[result['vendor']])})\s+", "", model, flags=re.I)
        result["model"], sources["model"] = model, "rótulo"
        work = work.replace(labeled_model.group(0), " ")
    else:
        rest = work
        if result["vendor"] and sources.get("vendor") == "fabricante conhecido":
            found = _find_vendor(rest)
            if found:
                match = re.search(rf"(?<![A-Za-z0-9]){re.escape(rest[found[1]:found[2]])}(?![A-Za-z0-9])", rest, re.I)
                if match:
                    rest = rest[:match.start()] + " " + rest[match.end():]
        rest = re.sub(rf"(?<![A-Za-z0-9])(?:{_MODEL_LABEL}|{_VENDOR_LABEL}|{_SERIAL_LABEL})\s*[:=#]?", " ", rest, flags=re.I)
        lines = [clean_value(part) for part in re.split(r"[\n;|]+", rest)]
        lines = [line for line in lines if line]
        if lines:
            result["model"], sources["model"] = lines[0], "texto restante"
            if len(lines) > 1:
                alternatives["model"] = lines
                warnings.append("Sobrou mais de um trecho de texto; conferi só o primeiro como modelo.")

    if result["model"] and sources.get("model") == "texto restante":
        warnings.append("O modelo é um palpite (não havia o rótulo 'Modelo:'); confira antes de cadastrar.")
    if result["serial"] is None and "serial" not in alternatives:
        warnings.append("Nenhum número de série reconhecido; use 'S/N:', 'Serial:' ou 'Service Tag:' antes do número.")
    result["sources"] = sources
    result["alternatives"] = alternatives
    result["warnings"] = warnings
    return result
