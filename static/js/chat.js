// ====== STEP-BY-STEP CHAT FUNCTIONALITY ====== */
class StepByStepChatManager {
    constructor() {
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.imageButton = document.getElementById('imageButton');
        this.fileInput = document.getElementById('fileInput');
        this.chatMessages = document.getElementById('chatMessages');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.charCount = document.getElementById('charCount');
        this.confirmationModal = document.getElementById('confirmationModal');
        this.currentStepIndicator = document.getElementById('currentStepIndicator');
        this.progressBar = document.getElementById('progressBar');
        
        this.orderData = {
            tipo: '',
            cabeza: {
                cabello: '',
                ojos: '',
                expresion: '',
                accesorios: ''
            },
            cuerpo: {
                torso_superior: '',
                torso_inferior: '',
                brazos: '',
                posicion: ''
            },
            piernas_pies: {
                calzado: '',
                posicion: '',
                accesorios: ''
            }
        };
        
        this.currentStep = 'tipo_figura';
        this.steps = [
            { id: 'tipo_figura', name: 'Tipo de Figura', icon: '🎯' },
            { id: 'cabeza', name: 'Cabeza', icon: '🧠' },
            { id: 'cuerpo', name: 'Cuerpo', icon: '👔' },
            { id: 'piernas_pies', name: 'Piernas y Pies', icon: '👟' }
        ];
        
        this.messages = [];
        this.userId = null;
        this.initEventListeners();
        this.addWelcomeMessage();
        this.updateStepIndicator();
    }

    initEventListeners() {
        // Message input
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.updateCharCount();
            this.sendButton.disabled = !this.messageInput.value.trim();
        });

        // Send button
        this.sendButton.addEventListener('click', () => {
            this.sendMessage();
        });

        // Image upload
        this.imageButton.addEventListener('click', () => {
            this.fileInput.click();
        });

        this.fileInput.addEventListener('change', (e) => {
            this.handleImageUpload(e.target.files);
        });

        // Modal buttons
        document.querySelectorAll('.modal-footer button').forEach(button => {
            button.addEventListener('click', () => {
                if (button.onclick) {
                    button.onclick();
                }
            });
        });

        // Focus input on load
        this.messageInput.focus();
    }

    addWelcomeMessage() {
        const welcomeMessage = document.createElement('div');
        welcomeMessage.className = 'system-message welcome';
        welcomeMessage.innerHTML = `
            <img src="/static/assets/cuix-logo.svg" alt="CUIX" class="bot-avatar-img">
            <div>
                <strong>🎯 ¡Bienvenido a tu Funko Personalizado!</strong><br><br>
                Para empezar, necesito saber: <strong>¿Qué tipo de figura Funko quieres?</strong><br><br>
                Ejemplos:<br>
                • Ingeniero<br>
                • Doctor<br>
                • Profesor<br>
                • Artista<br>
                • Bombero<br>
                • Cualquier profesión o personaje<br><br>
                <em>Escribe la profesión o tipo de personaje para comenzar...</em>
            </div>
        `;
        this.chatMessages.appendChild(welcomeMessage);
        this.scrollToBottom();
    }
    
    updateStepIndicator() {
        if (!this.currentStepIndicator) return;
        
        const currentStepData = this.steps.find(step => step.id === this.currentStep);
        if (currentStepData) {
            let progressHTML = '<div class="step-progress">';
            
            this.steps.forEach((step, index) => {
                const isCompleted = this.getStepIndex(step.id) < this.getStepIndex(this.currentStep);
                const isCurrent = step.id === this.currentStep;
                
                progressHTML += `
                    <div class="step-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}">
                        <div class="step-icon">${isCompleted ? '✅' : step.icon}</div>
                        <div class="step-name">${step.name}</div>
                    </div>
                `;
            });
            
            progressHTML += '</div>';
            this.currentStepIndicator.innerHTML = progressHTML;
        }
    }
    
    getStepIndex(stepId) {
        return this.steps.findIndex(step => step.id === stepId);
    }

    sendMessage() {
        const message = this.messageInput.value.trim();
        
        if (!message) return;

        this.displayMessage(message, 'user');
        this.messages.push({ role: 'user', content: message, timestamp: new Date().toISOString() });

        // Limpiar input inmediatamente
        this.messageInput.value = '';
        this.messageInput.setAttribute('value', '');
        
        // Segunda limpieza después de un pequeño delay
        setTimeout(() => {
            this.messageInput.value = '';
            this.messageInput.setAttribute('value', '');
        }, 10);
        
        // Tercera limpieza con setTimeout adicional
        setTimeout(() => {
            this.messageInput.value = '';
            this.messageInput.setAttribute('value', '');
        }, 50);
        
        this.updateCharCount();
        this.sendButton.disabled = true;
        this.showLoading();

        const messageData = {
            type: 'user_message',
            content: message,
            messages: this.messages,
            order_data: this.orderData,
            user_id: this.userId
        };

        if (window.wsManager) {
            const sent = window.wsManager.sendMessage(messageData);
            if (!sent) {
                this.hideLoading();
                this.showError('Error de conexión');
            }
        }
    }

    displayMessage(content, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        
        if (sender === 'user') {
            avatar.innerHTML = '<i class="fas fa-user"></i>';
        } else {
            avatar.innerHTML = '<img src="/static/assets/cuix-logo.svg" alt="CUIX" class="bot-avatar-img">';
        }

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = this.formatMessage(content);
        
        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.textContent = this.formatTime(new Date());

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
        messageDiv.appendChild(messageTime);

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();

        // Save message
        if (sender === 'assistant') {
            this.messages.push({ 
                role: 'assistant', 
                content: content, 
                timestamp: new Date().toISOString() 
            });
        }
    }

    formatMessage(content) {
        // Convert URLs to links
        let formatted = content.replace(
            /(https?:\/\/[^\s]+)/g,
            '<a href="$1" target="_blank" style="color: var(--primary-color);">$1</a>'
        );

        // Convert line breaks to <br>
        formatted = formatted.replace(/\n/g, '<br>');

        // Handle emojis
        formatted = formatted.replace(/:([a-z_]+):/g, (match, emojiName) => {
            const emojiMap = {
                'smile': '😊',
                'wink': '😉',
                'thumbs_up': '👍',
                'heart': '❤️',
                'star': '⭐',
                'crown': '👑',
                'gift': '🎁',
                'fire': '🔥',
                'rocket': '🚀',
                'tada': '🎉',
                'thinking': '🤔',
                'cool': '😎',
                'party': '🎊',
                'funko': '👑'
            };
            return emojiMap[emojiName] || match;
        });

        return formatted;
    }

    formatTime(date) {
        return date.toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    updateCharCount() {
        const current = this.messageInput.value.length;
        const max = this.messageInput.maxLength;
        this.charCount.textContent = `${current}/${max}`;
        
        if (current > max * 0.9) {
            this.charCount.style.color = 'var(--error-color)';
        } else {
            this.charCount.style.color = 'var(--dark-color)';
        }
    }

    updateOrderSummary(orderData) {
        if (orderData) {
            this.orderData = order_data;
            this.currentStep = orderData.current_step || 'tipo_figura';
            this.updateStepIndicator();
        }

        // Update UI
        const updates = {
            summaryTipo: { label: 'Tipo:', field: 'tipo', value: this.orderData.tipo || 'No especificado' },
            summaryVestimenta: { label: 'Vestimenta:', field: 'vestimenta', value: this.orderData.vestimenta || 'No especificado' },
            summaryCalzado: { label: 'Calzado:', field: 'calzado', value: this.orderData.calzado || 'No especificado' },
            summaryCabello: { label: 'Cabello:', field: 'cabello', value: this.orderData.cabello || 'No especificado' },
            summaryAccesorios: { label: 'Accesorios:', field: 'accesorios', value: this.orderData.accesorios || 'No especificado' }
        };

        Object.entries(updates).forEach(([elementId, config]) => {
            const element = document.getElementById(elementId);
            if (element) {
                const valueElement = element.querySelector('.value');
                if (valueElement) {
                    valueElement.textContent = config.value;
                    
                    // Add completion animation
                    element.classList.add('updated');
                    setTimeout(() => {
                        element.classList.remove('updated');
                    }, 500);
                }
            }
        });

        this.updateProgress();
    }

    updateProgress() {
        const fields = ['tipo', 'vestimenta', 'calzado', 'accesorios'];
        const completedFields = fields.filter(field => this.orderData[field] && this.orderData[field].trim() !== '').length;
        const progress = (completedFields.length / fields.length) * 100;

        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');

        if (progressFill) {
            progressFill.style.width = `${progress}%`;
        }

        if (progressText) {
            progressText.textContent = `${Math.round(progress)}% completo`;
        }

        // Add progress class based on completion
        if (progress >= 75) {
            progressFill.style.background = 'linear-gradient(90deg, var(--success-color), var(--primary-color))';
        } else if (progress >= 50) {
            progressFill.style.background = 'linear-gradient(90deg, var(--warning-color), var(--primary-color))';
        }
    }

    showLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.classList.add('active');
        }
    }

    hideLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.classList.remove('active');
        }
    }

    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'system-message error';
        errorDiv.innerHTML = `
            <i class="fas fa-exclamation-triangle"></i>
            <span>${message}</span>
        `;
        this.chatMessages.appendChild(errorDiv);
        this.scrollToBottom();

        setTimeout(() => {
            errorDiv.remove();
        }, 5000);
    }

    handleImageUpload(files) {
        Array.from(files).forEach((file, index) => {
            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                
                reader.onload = (e) => {
                    this.displayImageMessage(e.target.result, file.name);
                    
                    // Send image to server
                    const imageData = {
                        type: 'image_upload',
                        filename: file.name,
                        data: e.target.result.split(',')[1], // Remove data:image/...;base64, prefix
                        size: file.size
                    };
                    
                    if (window.wsManager) {
                        window.wsManager.sendMessage(imageData);
                    }
                };
                
                reader.readAsDataURL(file);
            }
        });
    }

    displayImageMessage(imageSrc, filename) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = '<i class="fas fa-user"></i>';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = `
            <div class="image-preview">
                <img src="${imageSrc}" alt="${filename}" style="max-width: 200px; max-height: 200px; border-radius: 8px;">
                <div class="image-info">
                    <i class="fas fa-image"></i> ${filename}
                </div>
            </div>
        `;
        
        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.textContent = this.formatTime(new Date());

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
        messageDiv.appendChild(messageTime);

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    scrollToBottom() {
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    showOrderDetails() {
        const orderDetails = document.getElementById('modalOrderDetails');
        if (orderDetails) {
            orderDetails.innerHTML = `
                <h4>📋 Detalles de tu Figura:</h4>
                <ul>
                    ${this.orderData.tipo ? `<li><strong>Tipo:</strong> ${this.orderData.tipo}</li>` : ''}
                    ${this.orderData.vestimenta ? `<li><strong>Vestimenta:</strong> ${this.orderData.vestimenta}</li>` : ''}
                    ${this.orderData.calzado ? `<li><strong>Calzado:</strong> ${this.orderData.calzado}</li>` : ''}
                    ${this.orderData.cabello ? `<li><strong>Cabello:</strong> ${this.orderData.cabello}</li>` : ''}
                    ${this.orderData.accesorios ? `<li><strong>Accesorios:</strong> ${this.orderData.accesorios}</li>` : ''}
                </ul>
            `;
        }
    }
}

// ====== MODAL FUNCTIONS ====== */
function showConfirmationModal(orderData) {
    const modal = document.getElementById('confirmationModal');
    if (modal && chatManager) {
        chatManager.showOrderDetails();
        modal.classList.add('active');
    }
}

function closeModal() {
    const modal = document.getElementById('confirmationModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

function startNewOrder() {
    closeModal();
    
    // Clear chat
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.innerHTML = '';
    }
    
    // Reset order data
    if (window.stepByStepChatManager) {
        window.stepByStepChatManager.orderData = {
            tipo: '',
            cabeza: {
                cabello: '',
                ojos: '',
                expresion: '',
                accesorios: ''
            },
            cuerpo: {
                torso_superior: '',
                torso_inferior: '',
                brazos: '',
                posicion: ''
            },
            piernas_pies: {
                calzado: '',
                posicion: '',
                accesorios: ''
            }
        };
        window.stepByStepChatManager.messages = [];
        window.stepByStepChatManager.currentStep = 'tipo_figura';
        window.stepByStepChatManager.updateStepIndicator();
        window.stepByStepChatManager.addWelcomeMessage();
    }
    
    // Focus input
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.focus();
    }
}

// ====== GLOBAL FUNCTIONS FOR COMPATIBILITY ====== */
function displayMessage(content, sender) {
    if (window.chatManager) {
        window.chatManager.displayMessage(content, sender);
    }
}

function updateOrderSummary(orderData) {
    if (window.chatManager) {
        window.chatManager.updateOrderSummary(orderData);
    }
}

function hideLoading() {
    if (window.chatManager) {
        window.chatManager.hideLoading();
    }
}

function showError(message) {
    if (window.chatManager) {
        window.chatManager.showError(message);
    }
}

// ====== INITIALIZATION ====== */
let stepByStepChatManager;

document.addEventListener('DOMContentLoaded', () => {
    stepByStepChatManager = new StepByStepChatManager();
    
    // Make functions globally available
    window.stepByStepChatManager = stepByStepChatManager;
    window.showConfirmationModal = showConfirmationModal;
    window.closeModal = closeModal;
    window.startNewOrder = startNewOrder;
    window.displayMessage = displayMessage;
    window.updateOrderSummary = updateOrderSummary;
    window.hideLoading = hideLoading;
    window.showError = showError;
});

// ====== COMPATIBILITY FUNCTIONS ====== */
function displayMessage(content, sender) {
    if (window.stepByStepChatManager) {
        window.stepByStepChatManager.displayMessage(content, sender);
    }
}

function updateOrderSummary(orderData) {
    if (window.stepByStepChatManager) {
        window.stepByStepChatManager.updateOrderSummary(orderData);
    }
}

function hideLoading() {
    if (window.stepByStepChatManager) {
        window.stepByStepChatManager.hideLoading();
    }
}

function showError(message) {
    if (window.stepByStepChatManager) {
        window.stepByStepChatManager.showError(message);
    }
}

// ====== ADDITIONAL STYLES FOR STEP-BY-STEP ====== */
const additionalStyles = `
    .step-progress {
        display: flex;
        justify-content: space-between;
        margin: 20px 0;
        padding: 10px;
        background: linear-gradient(135deg, rgba(78, 205, 196, 0.1), rgba(255, 107, 107, 0.1));
        border-radius: 12px;
        border: 1px solid rgba(255, 107, 107, 0.2);
    }
    
    .step-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 10px 5px;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    
    .step-item.completed {
        background: linear-gradient(135deg, #4ECDC4, #44A3AA);
        color: white;
    }
    
    .step-item.current {
        background: linear-gradient(135deg, var(--primary-color), #FFE66D);
        color: white;
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(255, 107, 107, 0.3);
    }
    
    .step-icon {
        font-size: 24px;
        margin-bottom: 5px;
    }
    
    .step-name {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .system-message.welcome {
        background: linear-gradient(135deg, var(--primary-color), #FFE66D);
        border-left: 4px solid var(--accent-color);
        font-size: 16px;
        line-height: 1.5;
    }
    
    .message-content strong {
        color: var(--primary-color);
        font-weight: 700;
    }
    
    .image-preview {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-direction: column;
    }
    
    .image-info {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.8);
        margin-top: 5px;
    }
    
    .system-message.error {
        background: linear-gradient(135deg, var(--error-color), var(--error-color));
    }
    
    .summary-item.updated {
        background: linear-gradient(135deg, var(--accent-light), var(--accent-color));
        transform: translateX(5px);
    }
    
    .in-page-notification {
        position: fixed;
        top: 20px;
        right: 20px;
        background: var(--error-color);
        color: white;
        padding: 15px 20px;
        border-radius: var(--border-radius);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        z-index: 3000;
        max-width: 300px;
        animation: slideIn 0.3s ease-out;
    }
    
    .in-page-notification strong {
        display: block;
        margin-bottom: 5px;
    }
`;

// Add styles to head
const styleSheet = document.createElement('style');
styleSheet.textContent = additionalStyles;
document.head.appendChild(styleSheet);