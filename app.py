from flask import Flask, render_template, request, jsonify, session, make_response
from flask_socketio import SocketIO, emit, send, join_room, leave_room
import uuid
import json
import logging
import time
from datetime import datetime
import sys
import os
import sqlite3
import threading
import mysql.connector
from mysql.connector import pooling
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formataddr
import base64
import hashlib
import secrets

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/livechat.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'funko-live-chat-secret-key-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Configure SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============= MYSQL CONFIGURATION =============
MYSQL_CONFIG = {
    'host': '172.25.80.1',
    'user': 'root',
    'password': 'root',
    'database': 'cuix_db',
    'pool_name': 'cuix_pool',
    'pool_size': 5,
    'connect_timeout': 3
}

db_pool = None
try:
    db_pool = pooling.MySQLConnectionPool(**MYSQL_CONFIG)
    logger.info("MySQL connection pool created successfully")
except Exception as e:
    logger.warning(f"MySQL not available, using SQLite: {e}")
    db_pool = None

def get_db_connection():
    """Get MySQL database connection"""
    if db_pool:
        try:
            return db_pool.get_connection()
        except Exception as e:
            logger.error(f"Error getting connection from pool: {e}")
    return None

def get_mysql_connection():
    """Get a new MySQL connection (alternative)"""
    try:
        return mysql.connector.connect(**MYSQL_CONFIG)
    except Exception as e:
        logger.error(f"MySQL connection error: {e}")
        return None

class ResponseManager:
    """Manages predefined responses for the chat system without AI"""

    def __init__(self):
        self.responses = {
            'greeting': [
                "¡Hola! Soy tu asistente Funko y estoy aquí para ayudarte a crear tu figura personalizada. 🎯",
                "¡Bienvenido! Estoy listo para diseñar tu Funko único. Comencemos con los detalles. 🎨",
                "¡Hola! Vamos a crear tu figura Funko personalizada paso a paso. ¡Empecemos! 🚀"
            ],
            'acknowledgment': [
                "Entendido perfectamente.",
                "¡Excelente detalle!",
                "Perfecto, he anotado eso.",
                "¡Genio! Me encanta esa idea.",
                "Entendido, continuemos con eso.",
                "¡Perfecto! Agregado a tu diseño."
            ],
            'continue_prompt': [
                "¿Hay algo más que quieras agregar a esta sección?",
                "¿Algun otro detalle para esta parte?",
                "¿Te gustaría añadir algo más aquí?",
                "¿Estás listo/a para continuar con la siguiente sección?"
            ],
            'step_complete': [
                "¡Perfecto! He completado esta sección de tu Funko.",
                "¡Excelente! Esta parte está lista.",
                "¡Genio! Sección completada con éxito.",
                "¡Perfecto! Detalles guardados correctamente."
            ],
            'next_section': [
                "Ahora vamos con la siguiente sección.",
                "Continuemos con el siguiente paso.",
                "Pasemos a la siguiente parte de tu diseño.",
                "Excelente, ahora sigamos adelante."
            ],
            'confirmation_positive': [
                "¡Perfecto! Tu pedido ha sido confirmado.",
                "¡Excelente! Todo está correcto.",
                "¡Genio! Confirmación recibida.",
                "¡Perfecto! Pedido confirmado exitosamente."
            ],
            'confirmation_negative': [
                "Entendido. Vamos a corregir los detalles.",
                "No hay problema. Revisemos qué cambiar.",
                "Perfecto, vamos a ajustar tu diseño.",
                "Entendido. Corrijamos lo necesario."
            ],
            'error_generic': [
                "Lo siento, tuve un problema. Por favor intenta nuevamente.",
                "Ha ocurrido un error. Por favor repite tu mensaje.",
                "Disculpa, no entendí. ¿Podrías repetirlo?",
                "Tuve un problema técnico. Por favor intenta de nuevo."
            ],
            'order_complete': [
                "¡Felicidades! Tu Funko personalizado está completo. 🎉",
                "¡Excelente! Hemos terminado tu diseño Funko. 🎯",
                "¡Perfecto! Tu figura está lista para producción. 🚀",
                "¡Genio! Tu Funko personalizado está finalizado. ✨"
            ]
        }

    def get_response(self, response_type, context=None):
        """Get a predefined response based on type and context"""
        import random

        if response_type in self.responses:
            responses = self.responses[response_type]
            base_response = random.choice(responses)

            # Add context-specific modifications
            if context:
                if context.get('step_name'):
                    base_response += f" Sección: {context['step_name']}"
                if context.get('next_prompt'):
                    base_response += f"\n\n{context['next_prompt']}"
                if context.get('summary'):
                    base_response += f"\n\n{context['summary']}"

            return base_response

        return self.responses['acknowledgment'][0]

    def generate_step_response(self, step_id, message_content, order_data):
        """Generate appropriate response for current step"""
        message_lower = message_content.lower()

        # Check for continuation signals
        continue_signals = ['siguiente', 'listo', 'terminado', 'continuar', 'avanzar', 'ya está', 'eso es todo', 'pasemos', 'pase al siguiente']
        is_continue = any(signal in message_lower for signal in continue_signals)

        # Check for completion signals
        completion_signals = ['listo', 'terminado', 'completado', 'fin', 'acabado']
        is_complete = any(signal in message_lower for signal in completion_signals)

        if is_continue or is_complete:
            return self.get_response('step_complete') + " " + self.get_response('next_section')
        else:
            return self.get_response('acknowledgment') + " " + self.get_response('continue_prompt')

class ConversationManager:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Initialize SQLite database for conversations"""
        try:
            conn = sqlite3.connect('conversations.db')
            cursor = conn.cursor()

            # Create conversations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    order_data TEXT,
                    status TEXT DEFAULT 'active'
                )
            ''')

            # Create messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
                )
            ''')

            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization error: {e}")

    def get_or_create_conversation(self, user_id):
        """Get existing conversation or create new one"""
        try:
            conn = sqlite3.connect('conversations.db')
            cursor = conn.cursor()

            # Check if conversation exists
            cursor.execute('SELECT id, order_data FROM conversations WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            if result:
                conv_id, order_data = result
                order_data = json.loads(order_data) if order_data else {}
            else:
                # Create new conversation
                cursor.execute('''
                    INSERT INTO conversations (user_id, order_data) VALUES (?, ?)
                ''', (user_id, json.dumps({})))
                conn.commit()
                conv_id = cursor.lastrowid
                order_data = {}

            conn.close()
            return conv_id, order_data

        except Exception as e:
            logger.error(f"Error getting/creating conversation: {e}")
            return None, {}

    def save_message(self, user_id, role, content, order_data=None):
        """Save message to database"""
        try:
            conn = sqlite3.connect('conversations.db')
            cursor = conn.cursor()

            # Get conversation ID
            cursor.execute('SELECT id FROM conversations WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            if not result:
                # Create conversation if it doesn't exist
                cursor.execute('INSERT INTO conversations (user_id) VALUES (?)', (user_id,))
                conv_id = cursor.lastrowid
            else:
                conv_id = result[0]

            # Save message
            cursor.execute('''
                INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)
            ''', (conv_id, role, content))

            # Update order data if provided
            if order_data is not None:
                cursor.execute('''
                    UPDATE conversations
                    SET order_data = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (json.dumps(order_data), user_id))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error saving message: {e}")

    def get_conversation_history(self, user_id, limit=20):
        """Get conversation history for a user"""
        try:
            conn = sqlite3.connect('conversations.db')
            cursor = conn.cursor()

            cursor.execute('''
                SELECT role, content, timestamp
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.user_id = ?
                ORDER BY m.timestamp ASC
                LIMIT ?
            ''', (user_id, limit))

            messages = []
            for role, content, timestamp in cursor.fetchall():
                messages.append({
                    'role': role,
                    'content': content,
                    'timestamp': timestamp
                })

            conn.close()
            return messages

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []

    def update_order_data(self, user_id, order_data):
        """Update order data for a conversation"""
        try:
            conn = sqlite3.connect('conversations.db')
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE conversations
                SET order_data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (json.dumps(order_data), user_id))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating order data: {e}")

class FunkoOrderManager:
    def __init__(self):
        self.pasos_orden = [
            {
                'id': 'datos_cliente',
                'nombre': 'DATOS DEL CLIENTE',
                'descripcion': 'nombre y telefono del cliente',
                'prompt': "📱 **DATOS DE CONTACTO:**\n\nPara finalizar tu pedido, necesito tus datos:\n\n• **Nombre completo:**\n• **Número de WhatsApp:** (con código de país)\n\nEjemplo: Juan Pérez, +51 987654321\n\n¿Cuál es tu nombre y número de teléfono?",
                'key_field': 'datos_cliente'
            },
            {
                'id': 'cabeza',
                'nombre': 'CABEZA',
                'descripcion': 'detalles de la cabeza',
                'prompt': "🧠 **Vamos a diseñar la CABEZA de tu Funko:**\n\nPor favor, descríbeme en detalle:\n• **Cabello:** color, estilo, longitud\n• **Rostro:** forma, expresión, características especiales\n• **Accesorios:** casco, gafas, sombrero, diadema, etc.\n• **Otros detalles:** barba, bigote, maquillaje, etc.\n\nPuedes darme los detalles en varios mensajes si lo prefieres. Cuando termines, dime **'listo'** o **'continuar'**.\n\n¿Cómo quieres la cabeza de tu figura?",
                'key_field': 'cabeza'
            },
            {
                'id': 'parte_superior',
                'nombre': 'PARTE SUPERIOR DEL CUERPO',
                'descripcion': 'detalles del torso y brazos',
                'prompt': "👕 **Ahora la PARTE SUPERIOR DEL CUERPO:**\n\nDescribe el torso y brazos:\n• **Torso:** camisa, polo, suéter, chaleco, blusa (color y estilo)\n• **Brazos:** posición, tatuajes, relojes, brazalete\n• **Hombros:** hombreras, mochila, etc.\n\nPuedes agregar detalles en varios mensajes. Cuando termines, dime **'listo'** o **'continuar'**.\n\n¿Qué detalles quieres para la parte superior?",
                'key_field': 'parte_superior'
            },
            {
                'id': 'parte_inferior',
                'nombre': 'PARTE INFERIOR DEL CUERPO',
                'descripcion': 'detalles de cintura hacia abajo',
                'prompt': "👖 **Ahora la PARTE INFERIOR DEL CUERPO:**\n\nDescribe desde la cintura hacia abajo:\n• **Cintura/Cadera:** cinturón, faldas, shorts\n• **Piernas:** pantalón, jeans, vestido (estilo y color)\n• **Posición:** de pie, sentado, corriendo, saltando\n\nPuedes agregar detalles en varios mensajes. Cuando termines, dime **'listo'** o **'continuar'**.\n\n¿Cómo quieres la parte inferior del cuerpo?",
                'key_field': 'parte_inferior'
            },
            {
                'id': 'pies',
                'nombre': 'PIES',
                'descripcion': 'detalles del calzado',
                'prompt': "👟 **Finalmente los PIES y calzado:**\n\nDescribe:\n• **Calzado:** botas, tenis, zapatos, sandalias, zapatillas\n• **Estilo:** deportivo, formal, casual, color específico\n• **Detalles:** cordones, hebillas, plataforma, etc.\n\n¿Qué tipo de calzado quieres?",
                'key_field': 'pies'
            },
            {
                'id': 'fotos_referencia',
                'nombre': 'FOTOS DE REFERENCIA',
                'descripcion': 'imágenes de apoyo',
                'prompt': "📸 **FOTOS DE REFERENCIA (OBLIGATORIO):**\n\nPor favor sube al menos una imagen de referencia para tu Funko.\n\nUsa el botón de imagen 🖼️ para subir fotos.\n\n• Si ya subiste tus fotos, escribe **'listo'** para continuar.\n• Si no tienes fotos, escribe **'no tengo'**.",
                'key_field': 'fotos_referencia'
            },
            {
                'id': 'detalles_adicionales',
                'nombre': 'DETALLES ADICIONALES',
                'descripcion': 'elementos extra',
                'prompt': "✨ **DETALLES ADICIONALES:**\n\n¿Hay algo más que debamos considerar?\n• **Accesorios extra:** bolso, herramienta, mascota, etc.\n• **Base o soporte:** texto en la base, logo, etc.\n• **Notas especiales:** cualquier detalle importante\n\n¿Algo más que agregar?",
                'key_field': 'detalles_adicionales'
            },
            {
                'id': 'confirmacion',
                'nombre': 'CONFIRMACIÓN FINAL',
                'descripcion': 'confirmar todo el pedido',
                'prompt': "📋 **¡REVISIÓN FINAL DEL PEDIDO!**\n\nPor favor, revisa cuidadosamente todos los detalles:\n\n{RESUMEN_COMPLETO}\n\n**¿Está todo CORRECTO?**\n\nResponde:\n• **SÍ** - para confirmar y enviar tu pedido\n• **NO** - para corregir algo\n• **CAMBIAR [sección]** - para modificar una parte específica\n\nEscribe tu respuesta:",
                'key_field': 'confirmacion'
            }
        ]

        # Removed default_order from __init__ to avoid mutable state issues
        # We will use a method to get a fresh copy

    @property
    def default_order(self):
        """Return a fresh copy of default order structure"""
        return {
            'datos_cliente': '',
            'cabeza': '',
            'parte_superior': '',
            'parte_inferior': '',
            'pies': '',
            'detalles_adicionales': '',
            'fotos_referencia': [],
            'fotos_comentarios': '',
            'confirmacion': ''
        }

    def get_current_step(self, order_data):
        """Determinar en qué paso está el pedido"""
        if not order_data:
            return self.pasos_orden[0]

        # Check if current step has data
        for i, paso in enumerate(self.pasos_orden):
            if not self._is_step_complete(order_data, paso):
                return paso

        return None  # Completado

    def _is_step_complete(self, order_data, paso):
        """Check if a specific step is complete"""
        if paso['id'] == 'confirmacion':
            return False  # La confirmación es manual

        key_field = paso['key_field']

        # Special logic for photo step
        if key_field == 'fotos_referencia':
            has_photos = len(order_data.get('fotos_referencia', [])) > 0
            has_comments = bool(order_data.get('fotos_comentarios', '').strip())
            return has_photos or has_comments

        # Special logic for detalles_adicionales (optional)
        if key_field == 'detalles_adicionales':
            # It's always "complete" in terms of not blocking, BUT to be a step in the flow
            # we need to know if we should move past it.
            # In our new auto-advance logic, we move next if it HAS content.
            # If it's empty, get_current_step will return it, so we stop there.
            # This matches "part of the flow".
            pass

        # NUEVA LÓGICA: Una sección está completa si tiene contenido
        value = order_data.get(key_field, '')
        has_content = bool(value and value.strip())

        return has_content

    def get_next_step(self, current_step_id):
        """Get the next step after current one"""
        for i, paso in enumerate(self.pasos_orden):
            if paso['id'] == current_step_id and i + 1 < len(self.pasos_orden):
                return self.pasos_orden[i + 1]
        return None

    def extract_step_info(self, message, step_id):
        """Extract information specific to the current step"""
        message_clean = message.strip()
        extracted = self.default_order.copy() # Now uses property, so it's fresh dict
        # But wait, property returns new dict, so .copy() is redundant but safe.
        # Actually property returns new dict each time.
        # But 'fotos_referencia': [] is new list each time.
        # So shallow copy of return value of property is fine.
        # Actually better to just call property.
        extracted = self.default_order

        if step_id == 'datos_cliente':
            extracted['datos_cliente'] = message_clean
        
        elif step_id == 'cabeza':
            extracted['cabeza'] = message_clean

        elif step_id == 'parte_superior':
            extracted['parte_superior'] = message_clean

        elif step_id == 'parte_inferior':
            extracted['parte_inferior'] = message_clean

        elif step_id == 'pies':
            extracted['pies'] = message_clean

        elif step_id == 'detalles_adicionales':
            extracted['detalles_adicionales'] = message_clean

        elif step_id == 'fotos_referencia':
            # If user types text here, save it as comments about photos
            if message_clean:
                extracted['fotos_comentarios'] = message_clean

        elif step_id == 'confirmacion':
            # Extraer respuesta de confirmación
            message_lower = message_clean.lower()

            if any(word in message_lower for word in ['sí', 'si', 'confirmar', 'correcto', 'ok']):
                extracted['confirmacion'] = 'confirmado'
            elif any(word in message_lower for word in ['no', 'incorrecto', 'mal']):
                extracted['confirmacion'] = 'rechazado'
            elif 'cambiar' in message_lower:
                extracted['confirmacion'] = 'cambiar'
                # Extraer qué se quiere cambiar
                for section in ['cabeza', 'parte superior', 'parte inferior', 'pies', 'detalles']:
                    if section in message_lower:
                        extracted['cambiar_seccion'] = section
                        break
            else:
                extracted['confirmacion'] = 'pendiente'

        return extracted

    def get_step_by_id(self, step_id):
        """Get step object by ID"""
        for paso in self.pasos_orden:
            if paso['id'] == step_id:
                return paso
        return None

    def merge_order_data(self, current_order, new_data):
        """Merge new extracted data into current order"""
        if not current_order:
            return new_data

        for key, value in new_data.items():
            if key == 'fotos_referencia' and isinstance(value, list):
                # Mantener fotos existentes y añadir nuevas
                if key not in current_order:
                    current_order[key] = []
                current_order[key].extend(value)
            elif isinstance(value, str) and value.strip():
                # NUEVA LÓGICA: Reemplazar contenido para permitir ediciones
                if key != 'confirmacion':
                    current_order[key] = value
                else:
                    current_order[key] = value

        return current_order

    def get_completion_summary(self, order_data):
        """Generate a complete summary of the order"""
        if not order_data:
            return "No hay datos del pedido."

        summary = "**📋 RESUMEN COMPLETO DEL PEDIDO FUNKO:**\n\n"

        sections = [
            ('🧠', 'CABEZA', 'cabeza'),
            ('👕', 'PARTE SUPERIOR', 'parte_superior'),
            ('👖', 'PARTE INFERIOR', 'parte_inferior'),
            ('👟', 'PIES', 'pies'),
            ('✨', 'DETALLES ADICIONALES', 'detalles_adicionales')
        ]

        for emoji, title, key in sections:
            value = order_data.get(key, '')
            if value and value.strip():
                summary += f"{emoji} **{title}:**\n{value}\n\n"
            else:
                summary += f"{emoji} **{title}:** No especificado\n\n"

        # Fotos de referencia
        fotos = order_data.get('fotos_referencia', [])
        if fotos:
            summary += f"📸 **FOTOS DE REFERENCIA:** {len(fotos)} archivo(s) subido(s)\n\n"

        return summary

    def get_section_to_change(self, section_name):
        """Get the step ID for a section name"""
        section_mapping = {
            'cabeza': 'cabeza',
            'parte superior': 'parte_superior',
            'parte inferior': 'parte_inferior',
            'pies': 'pies',
            'detalles': 'detalles_adicionales'
        }
        return section_mapping.get(section_name.lower(), 'cabeza')

class EmailManager:
    def __init__(self):
        self.smtp_server = "mail.peru-code.com"
        self.smtp_port = 465
        self.smtp_username = "forms@peru-code.com"
        self.smtp_password = "1wVTFLsQIrt36OG9"
        self.from_email = "forms@peru-code.com"
        self.from_name = "Funko Live Chat"
        self.to_email = "cuicuix.studio@gmail.com"

    def save_order_to_db(self, order_data, user_id):
        """Guardar pedido en MySQL (tabla orders)"""
        try:
            conn = get_mysql_connection()
            if not conn:
                logger.warning("MySQL no disponible, usando SQLite")
                return self.save_order_to_sqlite(order_data, user_id)

            cursor = conn.cursor()

            # Generar descripción combinada del pedido
            description = f"Cabeza: {order_data.get('cabeza', '')}\n"
            description += f"Parte Superior: {order_data.get('parte_superior', '')}\n"
            description += f"Parte Inferior: {order_data.get('parte_inferior', '')}\n"
            description += f"Pies: {order_data.get('pies', '')}\n"
            description += f"Detalles: {order_data.get('detalles_adicionales', '')}"

            # Guardar como JSON en order_data
            import json
            order_json = json.dumps(order_data, ensure_ascii=False)

            cursor.execute('''
                INSERT INTO orders (user_id, customer_name, customer_phone, order_type, order_data, price, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ''', (
                user_id,
                'Cliente Web',
                '',
                'Funko Personalizado',
                order_json,
                0,
                'pending'
            ))

            conn.commit()
            order_id = cursor.lastrowid
            conn.close()

            logger.info(f"Pedido {order_id} guardado en MySQL")
            return order_id

        except Exception as e:
            logger.error(f"Error guardando pedido en MySQL: {str(e)}")
            # Fallback a SQLite
            return self.save_order_to_sqlite(order_data, user_id)

    def save_order_to_sqlite(self, order_data, user_id):
        """Fallback: guardar pedido en SQLite"""
        try:
            conn = sqlite3.connect('conversations.db')
            cursor = conn.cursor()

            description = f"Cabeza: {order_data.get('cabeza', '')}\n"
            description += f"Parte Superior: {order_data.get('parte_superior', '')}\n"
            description += f"Parte Inferior: {order_data.get('parte_inferior', '')}\n"
            description += f"Pies: {order_data.get('pies', '')}\n"
            description += f"Detalles: {order_data.get('detalles_adicionales', '')}"

            cursor.execute('''
                INSERT INTO orders (user_id, cliente, customer_phone, tipo, description, clothing, shoes, accessories, price, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                'Cliente Web',
                '',
                'Funko Personalizado',
                description,
                order_data.get('parte_superior', ''),
                order_data.get('pies', ''),
                order_data.get('detalles_adicionales', ''),
                0,
                'pending',
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            conn.commit()
            order_id = cursor.lastrowid
            conn.close()

            logger.info(f"Pedido {order_id} guardado en SQLite")
            return order_id

        except Exception as e:
            logger.error(f"Error guardando pedido en SQLite: {str(e)}")
            return None

    def send_order_email(self, order_data, user_id):
        """Enviar correo electrónico con el resumen del pedido"""
        try:
            msg = MIMEMultipart()
            msg['From'] = formataddr((self.from_name, self.from_email))
            msg['To'] = self.to_email
            msg['Subject'] = f"🎯 Nuevo Pedido Funko Personalizado - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            html_content = self.generate_order_html(order_data, user_id)
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)

            # Attach photos
            fotos = order_data.get('fotos_referencia', [])
            for i, foto in enumerate(fotos):
                try:
                    # Check if data has header (e.g. "data:image/png;base64,")
                    img_data_str = foto.get('data', '')
                    if ',' in img_data_str:
                        img_data_str = img_data_str.split(',')[1]

                    img_data = base64.b64decode(img_data_str)
                    img_filename = foto.get('filename', f'referencia_{i+1}.jpg')

                    # Guess content type based on extension or default to jpeg
                    maintype = 'image'
                    subtype = 'jpeg'
                    if img_filename.lower().endswith('.png'):
                        subtype = 'png'
                    elif img_filename.lower().endswith('.gif'):
                        subtype = 'gif'

                    img = MIMEImage(img_data, _subtype=subtype)
                    img.add_header('Content-Disposition', 'attachment', filename=img_filename)
                    msg.attach(img)
                except Exception as e:
                    logger.error(f"Error attaching image {i}: {str(e)}")

            # Usar SMTP_SSL para puerto 465 (SSL directo)
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.from_email, [self.to_email, self.from_email], msg.as_string())

            logger.info(f"Email enviado exitosamente para pedido")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Error de autenticación SMTP: {str(e)}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"Error SMTP: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error enviando correo: {str(e)}")
            return False

    def generate_order_html(self, order_data, user_id):
        """Generar contenido HTML para el correo del pedido"""
        order_date = datetime.now().strftime('%d/%m/%Y a las %H:%M')

        sections = [
            ('🧠', 'CABEZA', 'cabeza'),
            ('👕', 'PARTE SUPERIOR DEL CUERPO', 'parte_superior'),
            ('👖', 'PARTE INFERIOR DEL CUERPO', 'parte_inferior'),
            ('👟', 'PIES', 'pies'),
            ('✨', 'DETALLES ADICIONALES', 'detalles_adicionales')
        ]

        sections_html = ""
        for emoji, title, key in sections:
            value = order_data.get(key, '')
            if value and value.strip():
                sections_html += f"""
                <div class="section">
                    <h3>{emoji} {title}</h3>
                    <p>{value.replace('\n', '<br>')}</p>
                </div>
                """
            else:
                sections_html += f"""
                <div class="section">
                    <h3>{emoji} {title}</h3>
                    <p><em>No especificado</em></p>
                </div>
                """

        # Fotos
        fotos = order_data.get('fotos_referencia', [])
        if fotos:
            fotos_html = "<div class='fotos-grid' style='display: flex; flex-wrap: wrap; gap: 10px;'>"
            for i, foto in enumerate(fotos):
                img_data = foto.get('data', '')
                img_filename = foto.get('filename', f'imagen_{i+1}')
                if img_data:
                    fotos_html += f"""
                    <div class="foto-item">
                        <img src="data:image/jpeg;base64,{img_data}" alt="{img_filename}" style="max-width: 150px; max-height: 150px; border-radius: 8px; border: 2px solid #FF6B6B;">
                    </div>
                    """
            fotos_html += "</div>"
        else:
            fotos_html = "<p><em>No se subieron fotos de referencia</em></p>"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Nuevo Pedido Funko</title>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
                .header {{ background-color: #FF6B6B; color: white; padding: 20px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .order-info {{ background-color: #f8f9fa; border-left: 4px solid #FF6B6B; padding: 15px; margin-bottom: 25px; }}
                .section {{ margin-bottom: 25px; }}
                .section h3 {{ color: #FF6B6B; border-bottom: 2px solid #FF6B6B; padding-bottom: 5px; margin-bottom: 15px; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Nuevo Pedido Funko Personalizado</h1>
                    <p>Recibido el {order_date}</p>
                </div>

                <div class="content">
                    <div class="order-info">
                        <p><strong>ID del Cliente:</strong> {user_id}</p>
                        <p><strong>Fecha y Hora:</strong> {order_date}</p>
                    </div>

                    {sections_html}

                    <div class="section">
                        <h3>📸 Fotos de Referencia</h3>
                        {fotos_html}
                    </div>

                    <div class="order-info">
                        <h3>⚠️ Próximos Pasos</h3>
                        <ol>
                            <li>Revisar los detalles del pedido</li>
                            <li>Contactar al cliente para confirmar precio</li>
                            <li>Establecer fecha de entrega</li>
                            <li>Procesar pago y envío</li>
                        </ol>
                    </div>
                </div>

                <div class="footer">
                    <p>Este correo fue generado automáticamente por Funko Live Chat (Sin IA)</p>
                    <p>Cuicuix Studio - Figuras Funko Personalizadas</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

# Initialize managers (NO OLLAMA)
response_manager = ResponseManager()
conversation_manager = ConversationManager()
order_manager = FunkoOrderManager()
email_manager = EmailManager()

# Active sessions storage
conversation_sessions = {}

# ============= AUTH DECORATOR =============
def require_auth(f):
    """Decorator to require authentication"""
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No autorizado'}), 401
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# Routes
@app.route('/')
def index():
    """Main chat page"""
    return render_template('index_new.html')

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard page"""
    response = make_response(render_template('admin.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/login')
@app.route('/login.html')
def login_page():
    """Login page"""
    return render_template('login.html')

@app.route('/admin.html')
def admin_html():
    """Admin HTML page"""
    response = make_response(render_template('admin.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/admin/orders')
@require_auth
def admin_get_orders():
    """Get all orders for admin from MySQL"""
    try:
        conn = get_mysql_connection()
        if not conn:
            return jsonify({'error': 'Database not available'}), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, user_id, customer_name, customer_phone, order_type, order_data, price, status, delivery_date, delivery_notes, created_at, updated_at
            FROM orders
            ORDER BY created_at DESC
            LIMIT 50
        ''')
        
        orders = []
        for row in cursor.fetchall():
            # Extraer datos del JSON
            order_data = row.get('order_data', {})
            if isinstance(order_data, str):
                try:
                    order_data = json.loads(order_data)
                except:
                    order_data = {}
            
            # Usar customer_name del registro o del JSON
            cliente = row['customer_name'] or order_data.get('nombre', 'Cliente Web')
            tipo = row['order_type'] or 'Funko Personalizado'
            
            # Extraer campos del JSON para descripción
            description = f"Cabeza: {order_data.get('cabeza', '')}\n"
            description += f"Parte Superior: {order_data.get('parte_superior', '')}\n"
            description += f"Parte Inferior: {order_data.get('parte_inferior', '')}\n"
            description += f"Pies: {order_data.get('pies', '')}\n"
            description += f"Detalles: {order_data.get('detalles_adicionales', '')}"
            
            orders.append({
                'id': row['id'],
                'user_id': row['user_id'],
                'cliente': cliente,
                'tipo': tipo,
                'description': description,
                'clothing': order_data.get('parte_superior', ''),
                'shoes': order_data.get('pies', ''),
                'accessories': order_data.get('detalles_adicionales', ''),
                'price': float(row['price']) if row['price'] else 0,
                'status': row['status'] or 'pending',
                'customer_phone': row.get('customer_phone', ''),
                'created_at': str(row['created_at']) if row['created_at'] else None,
                'updated_at': str(row['updated_at']) if row['updated_at'] else None
            })
        
        conn.close()
        return jsonify({'orders': orders})
        
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/order/<int:order_id>')
@require_auth
def admin_get_order_detail(order_id):
    """Get detailed order info from MySQL"""
    try:
        conn = get_mysql_connection()
        if not conn:
            return jsonify({'error': 'Database not available'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, user_id, customer_name, customer_phone, order_type, order_data, price, status, delivery_date, delivery_notes, created_at, updated_at
            FROM orders WHERE id = %s
        ''', (order_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'error': 'Order not found'}), 404

        order_data = row['order_data']
        if order_data:
            if isinstance(order_data, str):
                try:
                    order_data = json.loads(order_data)
                except:
                    pass

        return jsonify({
            'id': row['id'],
            'user_id': row['user_id'],
            'customer_name': row['customer_name'],
            'customer_phone': row['customer_phone'],
             'customer_name': row['customer_name'], 'order_type': row['order_type'], 'cliente': row['customer_name'] or 'Sin nombre', 'tipo': row['order_type'] or 'Funko',
            'order_data': order_data if isinstance(order_data, dict) else {},
            'price': float(row['price']) if row['price'] else 0,
            'status': row['status'],
            'created_at': str(row['created_at']),
            'updated_at': str(row['updated_at']),
            'is_complete': row['status'] == 'completed',
            'delivery_date': str(row['delivery_date']) if row['delivery_date'] else None,
            'delivery_notes': row['delivery_notes']
        })
    except Exception as e:
        logger.error(f"Error fetching order: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/order/<int:order_id>', methods=['PUT'])
@require_auth
def admin_update_order(order_id):
    """Update order"""
    try:
        data = request.json
        conn = get_mysql_connection()
        if not conn:
            return jsonify({'error': 'Database not available'}), 500

        cursor = conn.cursor()

        # Build update query
        updates = []
        values = []

        if 'customer_name' in data:
            updates.append("customer_name = %s")
            values.append(data['customer_name'])
        if 'customer_phone' in data:
            updates.append("customer_phone = %s")
            values.append(data['customer_phone'])
        if 'order_type' in data:
            updates.append("order_type = %s")
            values.append(data['order_type'])
        if 'price' in data:
            updates.append("price = %s")
            values.append(data['price'])
        if 'status' in data:
            updates.append("status = %s")
            values.append(data['status'])
        if 'delivery_date' in data:
            updates.append("delivery_date = %s")
            values.append(data['delivery_date'])
        if 'delivery_notes' in data:
            updates.append("delivery_notes = %s")
            values.append(data['delivery_notes'])

        if updates:
            values.append(order_id)
            query = f"UPDATE orders SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, values)
            conn.commit()

        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating order: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/whatsapp-link')
def admin_whatsapp_link():
    """Generate WhatsApp pre-filled link"""
    try:
        data = request.json
        telefono = data.get('telefono', '')
        mensaje = data.get('mensaje', '')

        # Clean phone number (remove spaces, dashes, etc)
        telefono = telefono.replace(' ', '').replace('-', '').replace('+', '')

        # Add country code if not present
        if telefono and not telefono.startswith('51'):  # 51 is Peru
            telefono = '51' + telefono

        # Generate WhatsApp link
        whatsapp_url = f"https://wa.me/{telefono}?text={requests.utils.quote(mensaje)}"

        return jsonify({'url': whatsapp_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= AUTHENTICATION (MySQL) =============

def load_users_mysql():
    """Load users from MySQL, fallback to SQLite"""
    # Intentar primero con MySQL
    conn = get_mysql_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, username, password_hash, full_name, email, role FROM admin_users")
            users = {}
            for row in cursor.fetchall():
                users[row['username']] = dict(row)
            conn.close()
            return users
        except Exception as e:
            logger.warning(f"MySQL error, using SQLite: {e}")
            conn.close()

    # Fallback a SQLite
    try:
        conn = sqlite3.connect('conversations.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password as password_hash, full_name, email, role FROM admin_users")
        users = {}
        for row in cursor.fetchall():
            users[row['username']] = dict(row)
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Error loading users from SQLite: {e}")
        return {}

def save_user_mysql(user_data):
    """Save user to MySQL"""
    conn = get_mysql_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin_users (username, password_hash, full_name, email, role)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_data['username'], user_data['password_hash'],
              user_data['full_name'], user_data['email'], user_data['role']))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving user: {e}")
        return False
    finally:
        conn.close()

def update_user_mysql(user_id, user_data):
    """Update user in MySQL"""
    conn = get_mysql_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE admin_users
            SET full_name = %s, email = %s, role = %s
            WHERE id = %s
        """, (user_data['full_name'], user_data['email'], user_data['role'], user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        return False
    finally:
        conn.close()

def delete_user_mysql(user_id):
    """Delete user from MySQL"""
    conn = get_mysql_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admin_users WHERE id = %s", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return False
    finally:
        conn.close()

def generate_token(user_id, username):
    """Generate auth token"""
    payload = f"{user_id}:{username}:{datetime.now().timestamp()}"
    return hashlib.sha256(payload.encode()).hexdigest()

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Admin login"""
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')

    users = load_users_mysql()

    for user in users.values():
        if user['username'] == username:
            # Aceptar contraseña hasheada o en texto plano (para fallback SQLite)
            hashed = hashlib.sha256(password.encode()).hexdigest()
            if user['password_hash'] == hashed or user['password_hash'] == password:
                token = generate_token(user['id'], username)
                return jsonify({
                    'success': True,
                    'token': token,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'name': user['full_name'],
                        'role': user['role']
                    }
                })

    return jsonify({'success': False, 'error': 'Credenciales incorrectas'}), 401

@app.route('/api/admin/users', methods=['GET'])
@require_auth
def admin_get_users():
    """Get all users from MySQL"""
    try:
        users = load_users_mysql()
        user_list = []
        for user in users.values():
            user_list.append({
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role']
            })
        return jsonify({'users': user_list})
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/user', methods=['POST'])
@require_auth
def admin_create_user():
    """Create new user in MySQL"""
    try:
        data = request.json

        # Check if username exists
        users = load_users_mysql()
        for user in users.values():
            if user['username'] == data['username']:
                return jsonify({'error': 'Usuario ya existe'}), 400

        new_user = {
            'username': data['username'],
            'password_hash': hashlib.sha256(data['password'].encode()).hexdigest(),
            'full_name': data['full_name'],
            'email': data['email'],
            'role': data.get('role', 'viewer')
        }

        if save_user_mysql(new_user):
            # Get the inserted user
            users = load_users_mysql()
            user = users[data['username']]
            return jsonify({'success': True, 'user': {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role']
            }})
        return jsonify({'error': 'Error al crear usuario'}), 500
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/user/<int:user_id>', methods=['PUT'])
@require_auth
def admin_update_user(user_id):
    """Update user in MySQL"""
    try:
        data = request.json

        user_data = {
            'full_name': data.get('full_name', ''),
            'email': data.get('email', ''),
            'role': data.get('role', 'viewer')
        }

        if update_user_mysql(user_id, user_data):
            return jsonify({'success': True})
        return jsonify({'error': 'Usuario no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/user/<int:user_id>', methods=['DELETE'])
@require_auth
def admin_delete_user(user_id):
    """Delete user from MySQL"""
    try:
        # Check if it's the last admin
        users = load_users_mysql()
        admin_count = sum(1 for u in users.values() if u['role'] == 'admin')

        user_to_delete = users.get(str(user_id)) or next((u for u in users.values() if u['id'] == user_id), None)

        if user_to_delete and user_to_delete['role'] == 'admin' and admin_count <= 1:
            return jsonify({'error': 'No puedes eliminar el único administrador'}), 400

        if delete_user_mysql(user_id):
            return jsonify({'success': True})
        return jsonify({'error': 'Usuario no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'ai_enabled': False,
        'active_sessions': len(conversation_sessions),
        'timestamp': datetime.now().isoformat()
    })

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connection"""
    user_id = str(uuid.uuid4())

    conv_id, order_data = conversation_manager.get_or_create_conversation(user_id)

    conversation_sessions[user_id] = {
        'conversation_id': conv_id,
        'order_data': order_data or order_manager.default_order.copy(),
        'current_step': order_manager.get_current_step(order_data),
        'connected_at': datetime.now().isoformat()
    }

    history = conversation_manager.get_conversation_history(user_id)

    emit('connection_status', {
        'status': 'online',
        'user_id': user_id,
        'initial_prompt': conversation_sessions[user_id]['current_step']['prompt'] if conversation_sessions[user_id]['current_step'] else response_manager.get_response('greeting'),
        'current_step': conversation_sessions[user_id]['current_step']['id'] if conversation_sessions[user_id]['current_step'] else None,
        'order_data': conversation_sessions[user_id]['order_data'],
        'conversation_history': history[-5:]
    })

    logger.info(f"Client connected: {user_id}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    for user_id in list(conversation_sessions.keys()):
        if conversation_sessions[user_id].get('connected_at'):
            del conversation_sessions[user_id]
            break

    logger.info("Client disconnected")

@socketio.on('user_message')
def handle_user_message(data):
    """Handle user message with sequential auto-advance"""
    try:
        user_id = data.get('user_id', str(uuid.uuid4()))
        message_content = data.get('content', '')

        if user_id not in conversation_sessions:
            conv_id, order_data = conversation_manager.get_or_create_conversation(user_id)
            conversation_sessions[user_id] = {
                'conversation_id': conv_id,
                'order_data': order_data if order_data else order_manager.default_order,
                'current_step': order_manager.pasos_orden[0],
                'connected_at': datetime.now().isoformat()
            }

        session = conversation_sessions[user_id]
        logger.info(f"Message from {user_id}: {message_content}")

        # Save user message
        conversation_manager.save_message(
            user_id,
            'user',
            message_content,
            session['order_data']
        )

        current_step = session['current_step']
        order_confirmed = False
        email_sent = False

        if current_step:
            extracted_info = order_manager.extract_step_info(message_content, current_step['id'])

            # Merge extracted information (OVERWRITE mode)
            session['order_data'] = order_manager.merge_order_data(
                session['order_data'],
                extracted_info
            )

            # Update order data in database immediately
            conversation_manager.update_order_data(user_id, session['order_data'])

            # Handle confirmation step
            if current_step['id'] == 'confirmacion':
                confirmation = session['order_data'].get('confirmacion', '')

                if confirmation == 'confirmado':
                    order_confirmed = True
                    # Guardar pedido en la base de datos
                    email_manager.save_order_to_db(session['order_data'], user_id)
                    # Enviar correo
                    email_sent = email_manager.send_order_email(session['order_data'], user_id)
                    session['current_step'] = None  # Pedido completado
                    ai_response = response_manager.get_response('confirmation_positive') + "\n\n" + response_manager.get_response('order_complete') + "\n\n📧 Tu pedido ha sido enviado exitosamente a cuicuix.studio@gmail.com. Nos pondremos en contacto contigo pronto para confirmar el precio y fecha de entrega.\n\n¡Gracias por tu pedido de figura Funko personalizada! 🎯"

                elif confirmation == 'rechazado':
                    session['order_data'] = order_manager.default_order
                    conversation_manager.update_order_data(user_id, session['order_data'])
                    session['current_step'] = order_manager.pasos_orden[0]
                    ai_response = response_manager.get_response('confirmation_negative') + "\n\nHe reiniciado el proceso de pedido. Vamos a empezar de nuevo.\n\n" + order_manager.pasos_orden[0]['prompt']

                elif confirmation == 'cambiar':
                    change_section = session['order_data'].get('cambiar_seccion', '')
                    target_step_id = order_manager.get_section_to_change(change_section)
                    target_step = order_manager.get_step_by_id(target_step_id)
                    if target_step:
                        session['current_step'] = target_step
                        ai_response = response_manager.get_response('acknowledgment') + f"\n\nVamos a modificar los detalles de {change_section}.\n\nPor favor, describe los nuevos detalles que quieres:"
                    else:
                         # Fallback if section unknown
                        next_incomplete_step = order_manager.get_current_step(session['order_data'])
                        session['current_step'] = next_incomplete_step
                        confirmation_prompt = order_manager.get_completion_summary(session['order_data'])
                        prompt = next_incomplete_step['prompt'].replace('{RESUMEN_COMPLETO}', confirmation_prompt)
                        ai_response = "No entendí qué sección cambiar. Volvamos a la confirmación.\n\n" + prompt

                else:
                    # Pendiente / No entendido
                    confirmation_prompt = order_manager.get_completion_summary(session['order_data'])
                    ai_response = f"Por favor, revisa el resumen y confirma:\n\n{confirmation_prompt}\n\n**¿Es correcta esta información?** Responde:\n• **SÍ** - para confirmar\n• **NO** - para corregir\n• **CAMBIAR [sección]** - para modificar algo específico"
            else:
                # Normal step: Content saved, find next INCOMPLETE step
                # This implements "resume where left off" logic
                next_incomplete_step = order_manager.get_current_step(session['order_data'])

                if next_incomplete_step:
                    session['current_step'] = next_incomplete_step

                    if next_incomplete_step['id'] == 'confirmacion':
                        confirmation_prompt = order_manager.get_completion_summary(session['order_data'])
                        # Ensure we use a fresh copy to avoid multiple replacements
                        next_step_copy = next_incomplete_step.copy()
                        prompt = next_step_copy['prompt'].replace('{RESUMEN_COMPLETO}', confirmation_prompt)
                        ai_response = "✅ ¡Guardado!\n\n" + prompt
                    else:
                        ai_response = f"✅ ¡Guardado! Pasemos a lo siguiente.\n\n{next_incomplete_step['prompt']}"
                else:
                    ai_response = "✅ ¡Todo listo! Revisemos el pedido."

        else:
            # Should not happen typically
            ai_response = response_manager.get_response('acknowledgment')

        # Save assistant response
        conversation_manager.save_message(
            user_id,
            'assistant',
            ai_response,
            session['order_data']
        )

        # Send response to client
        emit('ai_response', {
            'content': ai_response,
            'current_step': session['current_step']['id'] if session['current_step'] else None,
            'step_complete': True,
            'order_complete': session['current_step'] is None,
            'order_confirmed': order_confirmed,
            'email_sent': email_sent,
            'timestamp': datetime.now().isoformat()
        })

        # Update order summary
        emit('order_updated', {
            'order_data': session['order_data']
        })

    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        emit('ai_response', {
            'content': response_manager.get_response('error_generic'),
            'error': True
        })

@socketio.on('edit_section')
def handle_edit_section(data):
    """Handle request to edit a specific section"""
    user_id = data.get('user_id')
    section_key = data.get('section_key')

    if user_id in conversation_sessions:
        session = conversation_sessions[user_id]

        # Find step by key_field
        target_step = None
        for paso in order_manager.pasos_orden:
            if paso['key_field'] == section_key:
                target_step = paso
                break

        if target_step:
            session['current_step'] = target_step

            # Send prompt for that section
            ai_response = f"✏️ **Editando: {target_step['nombre']}**\n\n{target_step['prompt']}"

            # Save system notification
            conversation_manager.save_message(user_id, 'assistant', ai_response, session['order_data'])

            emit('ai_response', {
                'content': ai_response,
                'current_step': target_step['id'],
                'is_edit_mode': True,
                'timestamp': datetime.now().isoformat()
            })

            logger.info(f"User {user_id} switched to edit section: {section_key}")

@socketio.on('clear_section')
def handle_clear_section(data):
    """Handle request to clear a specific section"""
    user_id = data.get('user_id')
    section_key = data.get('section_key')

    if user_id in conversation_sessions:
        session = conversation_sessions[user_id]

        # Clear data
        if section_key in session['order_data']:
            session['order_data'][section_key] = '' if section_key != 'fotos_referencia' else []

            # Special case for photos: also clear comments
            if section_key == 'fotos_referencia':
                session['order_data']['fotos_comentarios'] = ''

            conversation_manager.update_order_data(user_id, session['order_data'])

            # Find step and switch to it
            target_step = None
            for paso in order_manager.pasos_orden:
                if paso['key_field'] == section_key:
                    target_step = paso
                    break

            if target_step:
                session['current_step'] = target_step
                ai_response = f"🗑️ **Sección borrada: {target_step['nombre']}**\n\n{target_step['prompt']}"

                conversation_manager.save_message(user_id, 'assistant', ai_response, session['order_data'])

                emit('ai_response', {
                    'content': ai_response,
                    'current_step': target_step['id'],
                    'timestamp': datetime.now().isoformat()
                })

                emit('order_updated', {'order_data': session['order_data']})
@socketio.on('image_upload')
def handle_image_upload(data):
    """Handle image upload for reference photos"""
    try:
        user_id = data.get('user_id')
        filename = data.get('filename')
        image_data = data.get('data')

        if user_id in conversation_sessions:
            session = conversation_sessions[user_id]

            # Save image data to order
            if 'fotos_referencia' not in session['order_data']:
                session['order_data']['fotos_referencia'] = []

            session['order_data']['fotos_referencia'].append({
                'filename': filename,
                'data': image_data,
                'timestamp': datetime.now().isoformat()
            })

            # Update database
            conversation_manager.update_order_data(user_id, session['order_data'])

            # Send success message
            emit('image_processed', {
                'filename': filename,
                'success': True
            })

            # If current step is fotos_referencia, we might want to acknowledge it
            # But the user might want to upload multiple.
            # We'll just update summary and let them manually say "listo" or type something if they want to proceed,
            # OR since we have auto-advance, maybe uploading a photo counts as "content"?
            # For now, let's just confirm upload.

            # Update order summary
            emit('order_updated', {
                'order_data': session['order_data']
            })

            logger.info(f"Image uploaded: {filename}")

            # AUTO-ADVANCE LOGIC
            # If we are currently in the 'fotos_referencia' step, check if we can advance
            current_step = session.get('current_step')
            if current_step and current_step['id'] == 'fotos_referencia':
                # Determine next step
                next_step = order_manager.get_current_step(session['order_data'])

                # If the next logical step is different from current (meaning this one is complete), advance
                if next_step and next_step['id'] != 'fotos_referencia':
                    session['current_step'] = next_step

                    # Generate response for the transition
                    ai_response = f"✅ ¡Foto recibida! Pasemos al siguiente paso.\n\n{next_step['prompt']}"

                    # Save assistant message
                    conversation_manager.save_message(user_id, 'assistant', ai_response, session['order_data'])

                    # Emit response to client
                    emit('ai_response', {
                        'content': ai_response,
                        'current_step': next_step['id'],
                        'step_complete': True,
                        'timestamp': datetime.now().isoformat()
                    })

    except Exception as e:
        logger.error(f"Error handling image upload: {str(e)}")
        emit('image_processed', {
            'filename': data.get('filename', 'unknown'),
            'success': False
        })

@socketio.on('reset_order')
def handle_reset_order(data):
    """Reset the order"""
    user_id = data.get('user_id', str(uuid.uuid4()))
    if user_id in conversation_sessions:
        conversation_sessions[user_id]['order_data'] = order_manager.default_order
        conversation_sessions[user_id]['current_step'] = order_manager.pasos_orden[0]

        conversation_manager.update_order_data(user_id, conversation_sessions[user_id]['order_data'])

        emit('order_reset', {
            'message': 'Pedido reiniciado correctamente.',
            'new_prompt': order_manager.pasos_orden[0]['prompt']
        })

@socketio.on('get_order_summary')
def handle_get_order_summary(data):
    """Get current order summary"""
    user_id = data.get('user_id', str(uuid.uuid4()))
    if user_id in conversation_sessions:
        session = conversation_sessions[user_id]
        summary = order_manager.get_completion_summary(session['order_data'])
        progress = []

        for paso in order_manager.pasos_orden:
            if order_manager._is_step_complete(session['order_data'], paso):
                progress.append(f"✅ {paso['nombre']}")
            else:
                progress.append(f"⏳ {paso['nombre']}")

        emit('order_summary', {
            'summary': summary,
            'progress': '\n'.join(progress),
            'current_step': session['current_step']['nombre'] if session['current_step'] else 'Completo'
        })

@socketio.on('borrar_seccion')
def handle_borrar_seccion(data):
    """Borrar una sección específica y solicitar que se complete de nuevo"""
    try:
        user_id = data.get('user_id')
        seccion = data.get('seccion')

        if user_id not in conversation_sessions:
            emit('seccion_borrada', {'success': False, 'error': 'Sesión no encontrada'})
            return

        session = conversation_sessions[user_id]

        # Guardar la sección actual donde estaba el usuario
        seccion_retorno = session['current_step']['id'] if session['current_step'] else None

        # Borrar el contenido de la sección
        if seccion == 'fotos':
            session['order_data']['fotos_referencia'] = []
        else:
            session['order_data'][seccion] = ''

        # Actualizar la base de datos
        conversation_manager.update_order_data(user_id, session['order_data'])

        # Buscar el paso correspondiente a la sección borrada
        paso_a_solicitar = None
        for paso in order_manager.pasos_orden:
            if paso['key_field'] == seccion:
                paso_a_solicitar = paso
                break

        if paso_a_solicitar:
            session['current_step'] = paso_a_solicitar
            prompt = paso_a_solicitar['prompt']

            # Si hay una sección de retorno, configurar para regresar después
            if seccion_retorno and seccion_retorno != seccion:
                session['seccion_retorno'] = seccion_retorno
                prompt += "\n\n⚠️ *Nota: Una vez completado, volverás a la sección donde estabas.*"

            emit('seccion_borrada', {
                'success': True,
                'order_data': session['order_data'],
                'nuevo_prompt': prompt,
                'seccion_retorno': seccion_retorno
            })

            # Enviar mensaje al chat
            emit('ai_response', {
                'content': f"🗑️ He borrado los datos de esta sección.\n\n{prompt}",
                'current_step': paso_a_solicitar['id'],
                'step_complete': False,
                'order_complete': False,
                'order_confirmed': False,
                'email_sent': False,
                'timestamp': datetime.now().isoformat()
            })

            emit('order_updated', {
                'order_data': session['order_data']
            })
        else:
            emit('seccion_borrada', {'success': False, 'error': 'Sección no encontrada'})

        logger.info(f"Sección '{seccion}' borrada para usuario {user_id}")

    except Exception as e:
        logger.error(f"Error al borrar sección: {str(e)}")
        emit('seccion_borrada', {'success': False, 'error': str(e)})

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Create necessary directories
    for directory in ['logs', 'uploads', 'reports', 'orders_data']:
        if not os.path.exists(directory):
            os.makedirs(directory)

    logger.info("Starting Funko Live Chat Server - NO AI VERSION")

    print("=" * 60)
    print("🎯 FUNKO LIVE CHAT - VERSIÓN SIN IA - INICIANDO 🎯")
    print("=" * 60)
    print("📍 Servidor corriendo en: http://localhost:5001")
    print("🤖 IA: DESACTIVADA (Sistema de respuestas predefinidas)")
    print("🌐 Abre tu navegador y visita esa URL")
    print("=" * 60)

    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=True,
        allow_unsafe_werkzeug=True
    )