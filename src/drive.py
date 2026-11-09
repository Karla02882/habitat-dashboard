"""INGESTA · EL DRIVE DE OBRA."""
from __future__ import annotations

import io
import json
import os
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CLAVE_ARCHIVO = RAIZ / "secretos" / "drive_cuenta_servicio.json"
CLAVE_ENV = "GOOGLE_CUENTA_SERVICIO"
CARPETA_RAIZ = "1foaGR9zHIlVcuU-jyJ7ko3TR-zL9m8zG"
ALCANCE = ["https://www.googleapis.com/auth/drive.readonly"]

MIME_SHEETS = "application/vnd.google-apps.spreadsheet"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_CARPETA = "application/vnd.google-apps.folder"


def _credencial():
    """La credencial, o None con el motivo escrito. Nunca revienta."""
    try:
        from google.oauth2 import service_account
    except ImportError:
        return None, "falta la librería google-auth"
    crudo = os.getenv(CLAVE_ENV, "").strip()
    if crudo:
        try:
            info = json.loads(crudo)
            return (service_account.Credentials.from_service_account_info(
                info, scopes=ALCANCE), "")
        except Exception as e:  # noqa: BLE001
            return None, f"{CLAVE_ENV} no se puede leer: {type(e).__name__}"
    if CLAVE_ARCHIVO.exists():
        try:
            return (service_account.Credentials.from_service_account_file(
                str(CLAVE_ARCHIVO), scopes=ALCANCE), "")
        except Exception as e:  # noqa: BLE001
            return None, f"la clave del disco no se puede leer: {type(e).__name__}"
    return None, (f"no hay credencial: ni {CLAVE_ENV} en el entorno ni "
                  f"secretos/{CLAVE_ARCHIVO.name} en el disco")


def _servicio():
    cred, motivo = _credencial()
    if cred is None:
        return None, motivo
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=cred, cache_discovery=False), ""
    except ImportError:
        return None, "falta la librería google-api-python-client"
    except Exception as e:  # noqa: BLE001
        return None, f"no se pudo abrir el Drive: {type(e).__name__}"


def hay_credencial() -> bool:
    cred, _ = _credencial()
    return cred is not None


def listar(carpeta_id: str, servicio=None) -> list[dict]:
    """Lo que hay adentro de una carpeta. Sin datos de personas."""
    srv = servicio
    if srv is None:
        srv, motivo = _servicio()
        if srv is None:
            raise RuntimeError(motivo)
    salida, pagina = [], None
    while True:
        r = srv.files().list(
            q=f"'{carpeta_id}' in parents and trashed = false",
            fields="nextPageToken, files(id,name,mimeType,size,modifiedTime)",
            pageSize=200, pageToken=pagina,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        for f in r.get("files", []):
            salida.append({
                "id": f["id"],
                "nombre": f["name"],
                "tipo": f["mimeType"],
                "carpeta": f["mimeType"] == MIME_CARPETA,
                "bytes": int(f.get("size") or 0),
                "fecha": (f.get("modifiedTime") or "")[:10],
            })
        pagina = r.get("nextPageToken")
        if not pagina:
            break
    return sorted(salida, key=lambda x: x["nombre"].upper())


def subcarpeta(nombre: str, servicio=None) -> str:
    """El id de una de las cinco subcarpetas, buscándola por su nombre."""
    limpio = " ".join(nombre.split()).upper()
    for f in listar(CARPETA_RAIZ, servicio):
        if f["carpeta"] and " ".join(f["nombre"].split()).upper() == limpio:
            return f["id"]
    return ""


def bajar(archivo: dict, destino: pathlib.Path, servicio=None) -> pathlib.Path | None:
    """Baja un archivo a `destino`. Un Google Sheets se exporta a xlsx."""
    from googleapiclient.http import MediaIoBaseDownload
    srv = servicio
    if srv is None:
        srv, motivo = _servicio()
        if srv is None:
            raise RuntimeError(motivo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        if archivo["tipo"] == MIME_SHEETS:
            datos = srv.files().export(fileId=archivo["id"], mimeType=MIME_XLSX).execute()
            destino.write_bytes(datos)
            return destino
        buf = io.BytesIO()
        baja = MediaIoBaseDownload(buf, srv.files().get_media(fileId=archivo["id"]))
        hecho = False
        while not hecho:
            _, hecho = baja.next_chunk()
        destino.write_bytes(buf.getvalue())
        return destino
    except Exception:  # noqa: BLE001 — un archivo que no baja no tumba el resto
        return None


def censo() -> dict:
    """Qué hay hoy en las cinco carpetas. Para la hoja Estado."""
    srv, motivo = _servicio()
    if srv is None:
        return {"hay": False, "motivo": motivo}
    try:
        hijos = listar(CARPETA_RAIZ, srv)
    except Exception as e:  # noqa: BLE001
        return {"hay": False,
                "motivo": f"no se pudo leer la carpeta: {type(e).__name__}"}
    carpetas = []
    for h in hijos:
        if not h["carpeta"]:
            continue
        try:
            dentro = listar(h["id"], srv)
        except Exception:  # noqa: BLE001
            dentro = []
        carpetas.append({
            "nombre": " ".join(h["nombre"].split()),
            "archivos": sum(1 for d in dentro if not d["carpeta"]),
            "carpetas": sum(1 for d in dentro if d["carpeta"]),
            "ultima": max((d["fecha"] for d in dentro), default=""),
        })
    return {"hay": True, "carpetas": carpetas,
            "fuente": "Drive · EJECUCIÓN DE PROYECTOS (cuenta de servicio, solo lectura)"}
