# 📧 Sistema de Envío Masivo de Correos

Sistema web para envío masivo de correos personalizados con Gmail, desarrollado para el Centro de Idiomas de la UNMSM.

## ✨ Características

- 📊 **Carga de datos**: Soporta archivos Excel (.xlsx, .xls) y CSV
- 📝 **Mensajes personalizados**: Variables dinámicas como `{{name}}` y `{{email}}`
- 📎 **Adjuntos**: Soporte para archivos PDF
- ✍️ **Firma automática**: Firma institucional que se agrega automáticamente
- 🔐 **Credenciales seguras**: Almacenamiento local de credenciales SMTP
- 📱 **Interfaz web**: Fácil de usar desde cualquier navegador

## 🚀 Instalación y Uso

### Requisitos
- Python 3.8 o superior
- Cuenta de Gmail con verificación en dos pasos habilitada
- Contraseña de aplicación de Gmail

### 1. Clonar el repositorio
```bash
git clone https://github.com/tu-usuario/correo-alumnos.git
cd correo-alumnos
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar credenciales
Crear archivo `.env` en la raíz del proyecto:
```env
SMTP_EMAIL=tu_correo@gmail.com
SMTP_APP_PASSWORD=tu_contraseña_de_aplicacion
SMTP_FROM_NAME=Centro de Idiomas
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

### 4. Ejecutar la aplicación
```bash
python app.py
```

### 5. Abrir en el navegador
Ir a: `http://localhost:5000`

## 📋 Cómo usar

1. **Subir archivo**: Carga tu archivo Excel/CSV con datos de alumnos
2. **Redactar mensaje**: Escribe el mensaje usando variables como `{{name}}`
3. **Configurar envío**: Las credenciales se cargan automáticamente desde `.env`
4. **Enviar**: El sistema enviará correos personalizados con firma automática

## 🔧 Variables disponibles en mensajes

- `{{name}}`: Nombre del alumno
- `{{email}}`: Correo del alumno

## 📁 Estructura del proyecto

```
correo-alumnos/
├── app.py                 # Aplicación principal
├── requirements.txt       # Dependencias
├── .env                   # Credenciales (no se sube a GitHub)
├── .gitignore            # Archivos a ignorar
├── README.md             # Este archivo
├── templates/            # Plantillas HTML
│   ├── base.html
│   ├── index.html
│   ├── preview.html
│   ├── confirm.html
│   ├── result.html
│   └── _signature.html   # Firma institucional
└── uploads/              # Archivos temporales
```

## 🔐 Seguridad

- Las credenciales se almacenan en `.env` (no se sube a GitHub)
- Los archivos subidos se almacenan temporalmente
- Conexión segura SMTP con TLS

## 🆘 Solución de problemas

### Error de autenticación Gmail
- Verificar que la verificación en dos pasos esté habilitada
- Usar contraseña de aplicación, no la contraseña normal
- Verificar que el correo y contraseña sean correctos

### Error de conexión SMTP
- Verificar configuración de firewall
- Verificar que el puerto 587 esté disponible

## 📞 Soporte

Para soporte técnico, contactar al Centro de Idiomas de la UNMSM.

## 📄 Licencia

Proyecto desarrollado para uso interno del Centro de Idiomas de la UNMSM.