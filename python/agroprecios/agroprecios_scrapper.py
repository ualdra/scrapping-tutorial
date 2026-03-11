#!/usr/bin/env python3
"""Scrapper incremental para Agroprecios.

- Consulta el endpoint PHP usado por la tabla de subastas.
- Recorre IDs de subasta y rango de fechas.
- Guarda/actualiza JSON como si fueran tablas.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.agroprecios.com/precios-subasta-tabla.php"
TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class ParsedRow:
    family_name: str
    product_name: str
    product_url: str | None
    cuts: list[int | None]


class JsonStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.subastas_path = self.data_dir / "subastas.json"
        self.familias_path = self.data_dir / "familias.json"
        self.productos_path = self.data_dir / "productos.json"
        self.precios_path = self.data_dir / "preciosubasta.json"

        self.subastas = self._load(self.subastas_path)
        self.familias = self._load(self.familias_path)
        self.productos = self._load(self.productos_path)
        self.precios = self._load(self.precios_path)

        self.subastas_by_id = {item["id"]: item for item in self.subastas}
        self.familias_by_name = {item["nombre"].strip().lower(): item for item in self.familias}
        self.productos_by_key = {
            (item["familia_id"], item["nombre"].strip().lower()): item for item in self.productos
        }

        self.precios_keys = {
            (
                item["subasta_id"],
                item["fecha"],
                item["producto_id"],
                item["corte"],
            )
            for item in self.precios
        }

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError:
                return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _next_id(items: list[dict[str, Any]]) -> int:
        return (max((item.get("id", 0) for item in items), default=0) + 1) if items else 1

    def upsert_subasta(self, subasta_id: int, nombre: str) -> None:
        stored = self.subastas_by_id.get(subasta_id)
        if stored is None:
            record = {"id": subasta_id, "nombre": nombre.strip()}
            self.subastas.append(record)
            self.subastas_by_id[subasta_id] = record
            return

        if nombre.strip() and stored.get("nombre") != nombre.strip():
            stored["nombre"] = nombre.strip()

    def get_or_create_familia(self, family_name: str) -> int:
        key = family_name.strip().lower()
        existing = self.familias_by_name.get(key)
        if existing is not None:
            return existing["id"]

        family_id = self._next_id(self.familias)
        record = {"id": family_id, "nombre": family_name.strip()}
        self.familias.append(record)
        self.familias_by_name[key] = record
        return family_id

    def get_or_create_producto(self, family_id: int, product_name: str, product_url: str | None) -> int:
        key = (family_id, product_name.strip().lower())
        existing = self.productos_by_key.get(key)
        if existing is not None:
            if product_url and not existing.get("url"):
                existing["url"] = product_url
            return existing["id"]

        product_id = self._next_id(self.productos)
        record = {
            "id": product_id,
            "familia_id": family_id,
            "nombre": product_name.strip(),
            "url": product_url,
        }
        self.productos.append(record)
        self.productos_by_key[key] = record
        return product_id

    def insert_precio(
        self,
        subasta_id: int,
        fecha_iso: str,
        producto_id: int,
        corte: int,
        precio: int,
    ) -> bool:
        key = (subasta_id, fecha_iso, producto_id, corte)
        if key in self.precios_keys:
            return False

        record = {
            "subasta_id": subasta_id,
            "fecha": fecha_iso,
            "producto_id": producto_id,
            "corte": corte,
            "precio": precio,
        }
        self.precios.append(record)
        self.precios_keys.add(key)
        return True

    def save(self) -> None:
        self._save_file(self.subastas_path, self.subastas)
        self._save_file(self.familias_path, self.familias)
        self._save_file(self.productos_path, self.productos)
        self._save_file(self.precios_path, self.precios)

    @staticmethod
    def _save_file(path: Path, data: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrapper de subastas de Agroprecios")
    parser.add_argument(
        "--lastdate",
        type=str,
        default=None,
        help="Fecha más reciente a consultar con formato dd/mm/yyyy (por defecto, hoy)",
    )
    parser.add_argument(
        "--maxdays",
        type=int,
        default=1,
        help="Número de días hacia atrás a consultar incluyendo lastdate (por defecto 1)",
    )
    parser.add_argument(
        "--maxsubastas",
        type=int,
        default=10,
        help="IDs de subasta a consultar desde 1 hasta maxsubastas (por defecto 10)",
    )
    return parser.parse_args()


def parse_input_date(date_str: str | None) -> date:
    if date_str is None:
        return datetime.now().date()
    return datetime.strptime(date_str, "%d/%m/%Y").date()


def date_to_php_format(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def date_to_iso(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def extract_table_date(soup: BeautifulSoup, fallback: date) -> date:
    title_cell = soup.select_one("table.tab_pre_sub td.titNombreder")
    if not title_cell:
        return fallback

    text = title_cell.get_text(" ", strip=True)
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", text)
    if not match:
        return fallback

    day, month, year = match.groups()
    return date(int(year), int(month), int(day))


def extract_auction_name(soup: BeautifulSoup, fallback_id: int) -> str:
    title_cell = soup.select_one("table.tab_pre_sub td.titNombreizq")
    if not title_cell:
        return f"Subasta {fallback_id}"

    name = title_cell.get_text(" ", strip=True)
    if not name:
        return f"Subasta {fallback_id}"
    return name


def parse_product_url(row: Any) -> str | None:
    onclick = row.get("onclick", "")
    if not onclick:
        return None

    match = re.search(r"window\.location\s*=\s*'([^']+)'", onclick)
    if match:
        return match.group(1)
    return None


def parse_cuts(row: Any) -> list[int | None]:
    values: list[int | None] = []
    for cell in row.select("td.txt"):
        text = cell.get_text(strip=True)
        if text == "-" or text == "":
            values.append(None)
            continue

        cleaned = re.sub(r"[^0-9]", "", text)
        values.append(int(cleaned) if cleaned else None)
    return values


def parse_rows(soup: BeautifulSoup) -> list[ParsedRow]:
    table = soup.select_one("table.tab_pre_pro")
    if table is None:
        return []

    rows: list[ParsedRow] = []
    current_family = ""

    for row in table.select("tr"):
        classes = row.get("class", [])
        if "familias_subasta" in classes:
            fam_cell = row.select_one("td[class^='fam']")
            if fam_cell:
                current_family = fam_cell.get_text(" ", strip=True)
            continue

        product_cell = row.select_one("td.pro")
        if product_cell is None or not current_family:
            continue

        product_name = product_cell.get_text(" ", strip=True)
        product_url = parse_product_url(row)
        cuts = parse_cuts(row)
        rows.append(
            ParsedRow(
                family_name=current_family,
                product_name=product_name,
                product_url=product_url,
                cuts=cuts,
            )
        )

    return rows


def has_error_response(html: str) -> bool:
    upper = html.upper()
    return "ERROR" in upper and "tab_pre_pro" not in html


def fetch_auction_html(session: requests.Session, subasta_id: int, for_date: date) -> str:
    params = {
        "sub": subasta_id,
        "fec": date_to_php_format(for_date),
        "op": 1,
    }
    response = session.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Referer": "https://www.agroprecios.com/",
        }
    )
    return session


def run_scrapper(lastdate: date, maxdays: int, maxsubastas: int, store: JsonStore) -> None:
    session = build_session()

    inserted_prices = 0
    queried = 0

    for day_offset in range(maxdays):
        current_day = lastdate - timedelta(days=day_offset)
        for subasta_id in range(1, maxsubastas + 1):
            queried += 1
            try:
                time.sleep(1)
                html = fetch_auction_html(session, subasta_id, current_day)
            except requests.RequestException as exc:
                print(
                    f"[WARN] Fallo consulta subasta={subasta_id} fecha={date_to_php_format(current_day)}: {exc}"
                )
                continue

            if has_error_response(html):
                print(
                    f"[INFO] Respuesta sin subasta válida para id={subasta_id} en {date_to_php_format(current_day)}"
                )
                continue

            soup = BeautifulSoup(html, "html.parser")
            auction_name = extract_auction_name(soup, subasta_id)
            displayed_date = extract_table_date(soup, current_day)
            displayed_date_iso = date_to_iso(displayed_date)
            parsed_rows = parse_rows(soup)

            if not parsed_rows:
                print(
                    f"[INFO] Sin filas de productos para subasta={subasta_id} fecha={displayed_date_iso}"
                )
                continue

            store.upsert_subasta(subasta_id, auction_name)

            for row in parsed_rows:
                family_id = store.get_or_create_familia(row.family_name)
                product_id = store.get_or_create_producto(
                    family_id,
                    row.product_name,
                    row.product_url,
                )

                for cut_index, price in enumerate(row.cuts, start=1):
                    if price is None:
                        continue
                    was_inserted = store.insert_precio(
                        subasta_id=subasta_id,
                        fecha_iso=displayed_date_iso,
                        producto_id=product_id,
                        corte=cut_index,
                        precio=price,
                    )
                    if was_inserted:
                        inserted_prices += 1

    store.save()
    print(
        f"[OK] Consultas ejecutadas: {queried}. Nuevos precios insertados: {inserted_prices}. "
        f"JSON actualizados en: {store.data_dir}"
    )


def validate_limits(maxdays: int, maxsubastas: int) -> None:
    if maxdays < 1:
        raise ValueError("maxdays debe ser >= 1")
    if maxsubastas < 1:
        raise ValueError("maxsubastas debe ser >= 1")


def main() -> None:
    args = parse_args()

    try:
        lastdate = parse_input_date(args.lastdate)
    except ValueError as exc:
        raise SystemExit(f"Formato de fecha inválido en --lastdate. Usa dd/mm/yyyy. Detalle: {exc}")

    try:
        validate_limits(args.maxdays, args.maxsubastas)
    except ValueError as exc:
        raise SystemExit(str(exc))

    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    store = JsonStore(data_dir)

    run_scrapper(lastdate=lastdate, maxdays=args.maxdays, maxsubastas=args.maxsubastas, store=store)


if __name__ == "__main__":
    main()
