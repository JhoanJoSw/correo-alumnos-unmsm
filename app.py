"""Aplicación Flask para envío masivo de correos con Gmail vía SMTP.

Flujo general:
1) Inicio (index): formulario para subir Excel/CSV y redactar el cuerpo del mensaje
2) prepare: guarda archivo, lee columnas y muestra vista previa + paso de mapeo
3) map_columns: mapea columnas (correo, nombre, asunto opcional) y muestra muestra renderizada
4) confirm (plantilla): pide credenciales SMTP, permite recordar en .env y adjuntar PDF
5) send_emails: envía correo personalizado por fila, con firma y adjunto opcional

Notas:
- Las credenciales pueden guardarse en .env si el usuario marca "Recordar credenciales".
- Se añade una espera entre envíos para no exceder límites de Gmail.
- La firma institucional se toma de templates/_signature.html
"""

import os
import io
import time
import base64
from typing import List, Dict

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename
import pandas as pd
from jinja2 import Template

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from dotenv import load_dotenv
import re
import html as html_lib

# Carpeta para almacenar archivos subidos temporalmente
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Extensiones permitidas para carga de datos
ALLOWED_EXTENSIONS = {'.xls', '.xlsx', '.csv'}

# Carga variables desde .env si existe
load_dotenv()

# Inicializa Flask y la clave de sesión
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-me-in-production')


def allowed_file(filename: str) -> bool:
	"""Valida si el archivo tiene una extensión soportada."""
	_, ext = os.path.splitext(filename.lower())
	return ext in ALLOWED_EXTENSIONS


def _get_env_default(key: str, fallback: str = '') -> str:
	"""Obtiene variable de entorno con valor por defecto si no existe."""
	val = os.environ.get(key)
	return val if val is not None else fallback


def _write_env_values(updates: Dict[str, str]) -> None:
	"""Crea o actualiza el archivo .env con pares clave=valor.

	Si una clave ya existe, la reemplaza. Si no, la agrega al final.
	"""
	env_path = os.path.join(os.path.dirname(__file__), '.env')
	lines: List[str] = []
	if os.path.exists(env_path):
		with open(env_path, 'r', encoding='utf-8') as f:
			lines = f.read().splitlines()
	mapping: Dict[str, str] = {}
	for line in lines:
		if '=' in line and not line.strip().startswith('#'):
			k = line.split('=', 1)[0].strip()
			mapping[k] = line
	for k, v in updates.items():
		safe_v = v.replace('\n', '').replace('\r', '')
		mapping[k] = f"{k}={safe_v}"
	new_lines = list(mapping.values())
	with open(env_path, 'w', encoding='utf-8') as f:
		f.write("\n".join(new_lines) + ("\n" if new_lines else ""))


def html_to_plain_text(value: str) -> str:
	"""Convierte un fragmento HTML a texto plano simple.

	- Reemplaza saltos de línea de <br> y cierre de párrafos por nuevas líneas
	- Elimina el resto de etiquetas
	- Desescapa entidades HTML
	"""
	if not value:
		return ''
	text = value
	# Saltos de línea comunes
	text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
	# Fin de párrafo como doble salto
	text = re.sub(r'</p\s*>', '\n\n', text, flags=re.IGNORECASE)
	# Eliminar cualquier otra etiqueta
	text = re.sub(r'<[^>]+>', '', text)
	# Desescapar entidades HTML (&nbsp;, &amp;, etc.)
	text = html_lib.unescape(text)
	return text.strip()


@app.route('/')
def index():
	"""Página inicial: formulario de carga y redacción del mensaje."""
	return render_template('index.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
	"""Sirve archivos subidos (solo para depuración o acceso controlado)."""
	return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/prepare', methods=['POST'])
def prepare():
	"""Recibe el archivo, valida y lee columnas; guarda datos en sesión.

	Devuelve una vista con columnas detectadas y una pequeña tabla de muestra
	para que el usuario pueda mapear campos en el siguiente paso.
	"""
	file = request.files.get('file')
	message_template = request.form.get('message_template', '')
	default_subject = request.form.get('default_subject', '')

	# Validaciones básicas de archivo
	if not file or file.filename == '':
		flash('Sube un archivo Excel o CSV')
		return redirect(url_for('index'))

	if not allowed_file(file.filename):
		flash('Formato no soportado. Usa .xls, .xlsx o .csv')
		return redirect(url_for('index'))

	# Guardar el archivo subido
	filename = secure_filename(file.filename)
	path = os.path.join(UPLOAD_FOLDER, filename)
	file.save(path)

	# Leer datos con pandas
	try:
		if filename.lower().endswith('.csv'):
			df = pd.read_csv(path)
		else:
			df = pd.read_excel(path)
	except Exception as exc:
		flash(f'No se pudo leer el archivo: {exc}')
		return redirect(url_for('index'))

	# Guardar estado de sesión y preparar columnas y muestra
	columns = list(df.columns)
	session['upload_path'] = path
	session['message_template'] = message_template
	session['default_subject'] = default_subject
	session['columns'] = columns

	return render_template('preview.html', columns=columns, sample=df.head(10).to_dict(orient='records'))


@app.route('/map', methods=['POST'])
def map_columns():
	"""Mapea las columnas seleccionadas y prepara los registros para envío."""
	email_col = request.form.get('email_col')
	name_col = request.form.get('name_col')
	subject_col = request.form.get('subject_col')

	upload_path = session.get('upload_path')
	if not upload_path:
		flash('Sesión expirada. Vuelve a subir el archivo.')
		return redirect(url_for('index'))

	# Releer el archivo definitivo
	try:
		if upload_path.lower().endswith('.csv'):
			df = pd.read_csv(upload_path)
		else:
			df = pd.read_excel(upload_path)
	except Exception as exc:
		flash(f'No se pudo leer el archivo: {exc}')
		return redirect(url_for('index'))

	# Validar columnas obligatorias
	missing = [c for c in [email_col, name_col] if not c or c not in df.columns]
	if missing:
		flash('Selecciona correctamente las columnas de correo y nombre.')
		return redirect(url_for('index'))

	# Construir registros normalizados
	records: List[Dict] = []
	for _, row in df.iterrows():
		record = {
			'email': str(row[email_col]).strip(),
			'name': str(row[name_col]).strip(),
		}
		if subject_col and subject_col in df.columns:
			record['subject'] = str(row[subject_col]).strip()
		records.append(record)

	# Guardar en sesión para el envío
	session['mapped_records'] = records
	session['email_col'] = email_col
	session['name_col'] = name_col
	session['subject_col'] = subject_col or ''

	# Renderizar muestras de los primeros registros para validar la plantilla
	message_template = session.get('message_template', '')
	default_subject = session.get('default_subject', '')

	rendered_samples = []
	for rec in records[:5]:
		try:
			body = Template(message_template).render(name=rec.get('name', ''), email=rec.get('email', ''))
			subject = rec.get('subject') or default_subject
			rendered_samples.append({'to': rec['email'], 'subject': subject, 'body': body})
		except Exception as exc:
			rendered_samples.append({'to': rec['email'], 'subject': '(error)', 'body': f'Error al renderizar: {exc}'})

	# Prefill SMTP desde .env (si existe)
	smtp_defaults = {
		'smtp_email': _get_env_default('SMTP_EMAIL', ''),
		'smtp_app_password': _get_env_default('SMTP_APP_PASSWORD', 'dgjr jxdm dske dxos'),
		'from_name': _get_env_default('SMTP_FROM_NAME', 'Centro de Idiomas'),
		'smtp_host': _get_env_default('SMTP_HOST', 'smtp.gmail.com'),
		'smtp_port': _get_env_default('SMTP_PORT', '587'),
	}

	return render_template('confirm.html', samples=rendered_samples, total=len(records), **smtp_defaults)


@app.route('/send', methods=['POST'])
def send_emails():
	"""Envía los correos personalizados con firma y adjunto opcional."""
	records: List[Dict] = session.get('mapped_records') or []
	if not records:
		flash('No hay destinatarios. Vuelve a subir el archivo.')
		return redirect(url_for('index'))

	message_template = session.get('message_template', '')
	default_subject = session.get('default_subject', '')

	# Credenciales SMTP ingresadas por el usuario
	smtp_email = request.form.get('smtp_email', '').strip()
	smtp_app_password = request.form.get('smtp_app_password', '').strip()
	from_name = request.form.get('from_name', '').strip() or 'Centro de Idiomas'
	smtp_host = request.form.get('smtp_host', 'smtp.gmail.com').strip() or 'smtp.gmail.com'
	smtp_port = int(request.form.get('smtp_port', '587'))
	remember = request.form.get('remember_credentials') == 'on'

	# Adjuntos PDF opcionales (múltiples)
	attachments: List[Dict[str, bytes]] = []

	# Soporte nuevo: múltiples archivos con name="attachments" (multiple)
	for f in request.files.getlist('attachments'):
		if f and f.filename:
			fname = secure_filename(f.filename)
			try:
				content = f.read()
				attachments.append({'name': fname, 'bytes': content})
			except Exception:
				pass

	# Compatibilidad hacia atrás: campo único 'attachment'
	legacy_attachment = request.files.get('attachment')
	if legacy_attachment and legacy_attachment.filename:
		fname = secure_filename(legacy_attachment.filename)
		try:
			content = legacy_attachment.read()
			attachments.append({'name': fname, 'bytes': content})
		except Exception:
			pass

	# Validación de credenciales
	if not smtp_email or not smtp_app_password:
		flash('Debes ingresar el correo remitente y la contraseña de aplicación.')
		return redirect(url_for('index'))

	# Cargar firma institucional (método directo)
	signature_text = ''
	try:
		signature_path = os.path.join(os.path.dirname(__file__), 'templates', '_signature.html')
		with open(signature_path, 'r', encoding='utf-8') as f:
			signature_html = f.read().strip()
		# Convertir HTML a texto plano para el correo
		signature_text = html_to_plain_text(signature_html)
		print(f"Firma HTML cargada: {repr(signature_html)}")
		print(f"Firma convertida a texto: {repr(signature_text)}")
		print(f"Longitud de la firma: {len(signature_text)} caracteres")
		print(f"Archivo de firma encontrado en: {signature_path}")
	except Exception as exc:
		print(f"Error cargando firma: {exc}")
		print(f"Intentando cargar desde: {os.path.join(os.path.dirname(__file__), 'templates', '_signature.html')}")
		# Firma de respaldo hardcodeada para pruebas
		signature_text = """Coordinación de Matrícula
Centro de Idiomas de la Universidad Nacional Mayor de San Marcos
Correo: personalcontratado31.flch@unmsm.edu.pe
Av. Universitaria, Calle Germán Amézaga Nº 375. Ciudad Universitaria, Lima"""
		print(f"Usando firma de respaldo: {repr(signature_text)}")

	# Conectar a SMTP con TLS y autenticación
	results = []
	try:
		server = smtplib.SMTP(smtp_host, smtp_port)
		server.ehlo()
		server.starttls()
		server.login(smtp_email, smtp_app_password)
	except Exception as exc:
		flash(f'No se pudo conectar a SMTP: {exc}')
		return redirect(url_for('index'))

	# Envío por cada destinatario
	for idx, rec in enumerate(records, start=1):
		to_addr = rec.get('email', '').strip()
		if not to_addr:
			results.append({'to': to_addr, 'status': 'error', 'detail': 'Correo vacío'})
			continue
		try:
			# Renderizar cuerpo con variables en texto plano
			body_text = Template(message_template).render(name=rec.get('name', ''), email=to_addr)
			
			# Agregar firma institucional al final (siempre)
			if signature_text:
				body_text = f"{body_text}\n\n{signature_text}"
				print(f"Firma agregada al mensaje para {to_addr}")
				print(f"Contenido completo del mensaje para {to_addr}:")
				print("=" * 50)
				print(body_text)
				print("=" * 50)
			else:
				print(f"ADVERTENCIA: No hay firma disponible para {to_addr}")
			subject = rec.get('subject') or default_subject or 'Comunicado'

			# Construir mensaje multi-parte (HTML + adjunto opcional)
			msg_root = MIMEMultipart()
			msg_root['To'] = to_addr
			msg_root['Subject'] = subject
			msg_root['From'] = formataddr((from_name, smtp_email))

			# Parte de texto plano
			msg_root.attach(MIMEText(body_text, 'plain', 'utf-8'))

			# Partes de adjuntos (solo PDFs si el usuario sube otros tipos)
			for att in attachments:
				att_name = att.get('name') or 'adjunto.pdf'
				att_bytes = att.get('bytes') or b''
				if not att_bytes:
					continue
				# Aceptar solo PDF explícitamente
				if not att_name.lower().endswith('.pdf'):
					continue
				part = MIMEApplication(att_bytes, Name=att_name)
				part['Content-Disposition'] = f'attachment; filename="{att_name}"'
				msg_root.attach(part)

			# Enviar
			server.sendmail(smtp_email, [to_addr], msg_root.as_string())
			results.append({'to': to_addr, 'status': 'enviado', 'detail': ''})

			# Pausa ligera por buenas prácticas con cuotas
			time.sleep(0.5)
		except Exception as exc:
			results.append({'to': to_addr, 'status': 'error', 'detail': str(exc)})

	# Cerrar conexión SMTP
	try:
		server.quit()
	except Exception:
		pass

	# Guardar credenciales en .env si el usuario lo solicitó (almacenamiento local)
	if remember:
		_write_env_values({
			'SMTP_EMAIL': smtp_email,
			'SMTP_APP_PASSWORD': smtp_app_password,
			'SMTP_FROM_NAME': from_name,
			'SMTP_HOST': smtp_host,
			'SMTP_PORT': str(smtp_port),
		})
		# Refrescar variables de entorno actuales
		os.environ['SMTP_EMAIL'] = smtp_email
		os.environ['SMTP_APP_PASSWORD'] = smtp_app_password
		os.environ['SMTP_FROM_NAME'] = from_name
		os.environ['SMTP_HOST'] = smtp_host
		os.environ['SMTP_PORT'] = str(smtp_port)

	# Mostrar reporte de resultados
	return render_template('result.html', results=results)


if __name__ == '__main__':
	# Obtener puerto de Railway o usar 5000 por defecto
	port = int(os.environ.get('PORT', 5000))
	# Ejecutar servidor
	app.run(host='0.0.0.0', port=port, debug=False)
