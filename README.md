# Habitat Cockpit

Plataforma web de gestión para Habitat Inmobiliaria. Consolida en un solo tablero la información de AXION, Kommo, ContaSis y Google Drive, con indicadores de ventas, cobranza, caja, finanzas, obras, marketing y CRM.

## Stack

- **Backend:** Python 3.13, servidor HTTP propio (`scripts/servidor.py`) con autenticación por roles.
- **Datos:** pandas y openpyxl. La ingesta está en `src/`.
- **Frontend:** HTML, CSS y JavaScript sin framework (`design/`). `scripts/armar_cockpit.py` une las hojas en `design/cockpit.html`.
- **App instalable:** PWA en `pwa/`.
- **Despliegue:** Render (`render.yaml`).

## Estructura

```text
src/        ingesta de fuentes y cálculo de indicadores
scripts/    servidor, generación del tablero y exportadores
design/     hojas, estilos y JavaScript del tablero
pwa/        manifest, service worker e íconos
assets/     logos
config/     metas, indicadores, cierres y saldos
data/       datos de referencia versionados (cierres y cronogramas)
```

## Ejecutar en local

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
cp .env.example .env
venv/Scripts/python -X utf8 scripts/generar_tablero.py
venv/Scripts/python -X utf8 scripts/servidor.py
```

Abrir `http://localhost:8777/design/cockpit.html`. En Linux o macOS, usar `venv/bin/` en lugar de `venv/Scripts/`.

Después de cambiar una hoja de `design/`, volver a armar el tablero:

```bash
venv/Scripts/python -X utf8 scripts/armar_cockpit.py
```

## Variables de entorno

| Variable | Uso |
|---|---|
| `AXION_API_BASE_URL` | URL de la API de AXION |
| `AXION_API_TOKEN` | Token de lectura de AXION |
| `KOMMO_SUBDOMINIO` | Subdominio de la cuenta de Kommo |
| `KOMMO_TOKEN` | Token de larga duración de Kommo |
| `GOOGLE_CUENTA_SERVICIO` | JSON de la cuenta de servicio de Google con acceso de lectura a la carpeta de Drive |
| `TABLERO_USUARIO` | Usuario de la cuenta administradora |
| `TABLERO_CLAVE` | Clave de la cuenta administradora |
| `TABLERO_USUARIOS` | Otras cuentas, con el formato `usuario:clave:rol`, separadas por coma |
| `TABLERO_SECRETO` | Secreto para firmar las sesiones |
| `TABLERO_REFRESCO_MIN` | Minutos entre actualizaciones del tablero (0 lo apaga) |
| `TABLERO_STOCK_MIN` | Minutos entre lecturas del stock en vivo (0 lo apaga) |
| `CONTROLES_CADA_HORAS` | Horas entre controles automáticos (0 los apaga) |

Roles disponibles: `admin`, `habitat`, `comercial`, `finanzas`, `obras`, `ventas` y `externo`.

## Conexiones

El código ya trae las integraciones. Las claves no van en el repositorio: se cargan en **Environment** de Render o en `.env`.

| Servicio | Dónde se obtiene |
|---|---|
| AXION (Base44) | Settings > Secrets > Personal access tokens, con permiso de lectura sobre la app |
| Kommo | Ajustes > Integraciones > integración privada, token de larga duración |
| Google Drive | Cuenta de servicio en Google Cloud, con la API de Drive activa; compartir con ella la carpeta de proyectos como Lector y pegar su JSON en `GOOGLE_CUENTA_SERVICIO` |

El identificador de la carpeta de Drive está en `src/drive.py`.

## Desplegar en Render

1. En Render, elegir **New > Blueprint** y conectar este repositorio.
2. Render lee `render.yaml` y crea el servicio web con su disco en `/var/data`.
3. Cargar en **Environment** los valores de las variables marcadas como `sync: false`.
4. Desplegar. La primera vez el tablero tarda unos minutos, porque se genera leyendo las fuentes.

El disco guarda lo que se escribe desde la aplicación: comentarios de morosos, informes, imágenes y cambios de stock.

## Cierres mensuales

Los cierres de ContaSis se importan con `scripts/importar_contasis.py`, que actualiza `config/contasis_mensual.json`.
