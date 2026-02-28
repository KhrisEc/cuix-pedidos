// ====== SOCKET.IO CONFIGURATION ====== */
class SocketIOManager {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.reconnectCount = 0;
        this.userId = null;
        this.connect();
    }

    connect() {
        try {
            console.log('Connecting to Socket.IO...');
            this.socket = io();
            
            this.socket.on('connect', () => {
                console.log('Socket.IO connected');
                this.isConnected = true;
                this.reconnectCount = 0;
                updateConnectionStatus('online');
            });
            
            this.socket.on('disconnect', () => {
                console.log('Socket.IO disconnected');
                this.isConnected = false;
                updateConnectionStatus('offline');
            });
            
            this.socket.on('connect_error', (error) => {
                console.error('Socket.IO connection error:', error);
                updateConnectionStatus('error');
            });
            
            // Handle connection_status to get user_id
            this.socket.on('connection_status', (data) => {
                console.log('Connection status:', data);
                if (data.user_id) {
                    this.userId = data.user_id;
                    console.log('User ID assigned:', this.userId);
                }
                updateConnectionStatus(data.status);
            });
            
            // Handle server events
            this.socket.on('ai_response', (data) => {
                console.log('AI response received:', data);
                this.handleMessage(data);
            });
            
            this.socket.on('order_updated', (data) => {
                console.log('Order updated:', data);
                updateOrderSummary(data.order_data);
            });
            
            this.socket.on('order_completed', (data) => {
                console.log('Order completed:', data);
                showConfirmationModal(data.order_data);
            });
            
            this.socket.on('connection_status', (data) => {
                console.log('Connection status:', data);
                updateConnectionStatus(data.status);
            });
            
            this.socket.on('image_processed', (data) => {
                console.log('Image processed:', data);
                if (data.success) {
                    hideLoading();
                } else {
                    showError('Error al procesar imagen');
                }
            });
            
            this.socket.on('heartbeat_response', (data) => {
                console.log('Heartbeat response:', data);
            });
            
        } catch (error) {
            console.error('Failed to create Socket.IO connection:', error);
        }
    }

    sendMessage(message) {
        if (this.isConnected && this.socket) {
            console.log('Sending message:', message);
            
            // Add user_id to message if available
            if (this.userId && message.type === 'user_message') {
                message.user_id = this.userId;
            }
            
            // Map message types to Socket.IO events
            switch (message.type) {
                case 'user_message':
                    this.socket.emit('user_message', message);
                    break;
                case 'image_upload':
                    this.socket.emit('image_upload', message);
                    break;
                case 'heartbeat':
                    this.socket.emit('heartbeat');
                    break;
                default:
                    console.log('Unknown message type:', message.type);
            }
            return true;
        } else {
            console.log('Socket.IO not connected');
            return false;
        }
    }

    handleMessage(data) {
        console.log('Handling message:', data);
        
        if (window.chatManager) {
            // Display AI response
            window.chatManager.displayMessage(data.content, 'assistant');
            
            // Update order summary if provided
            if (data.order_data) {
                window.chatManager.updateOrderSummary(data.order_data);
            }
            
            // Hide loading overlay
            window.chatManager.hideLoading();
        }
        
        // Call global functions for compatibility
        if (typeof displayMessage === 'function') {
            displayMessage(data.content, 'assistant');
        }
        if (typeof updateOrderSummary === 'function' && data.order_data) {
            updateOrderSummary(data.order_data);
        }
        if (typeof hideLoading === 'function') {
            hideLoading();
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.isConnected = false;
        }
    }
}

// ====== CONNECTION STATUS ====== */
function updateConnectionStatus(status) {
    const statusIndicator = document.querySelector('.status-indicator');
    const statusText = document.querySelector('.status-text');
    
    statusIndicator.className = `status-indicator ${status}`;
    
    switch (status) {
        case 'online':
            statusText.textContent = 'En línea';
            statusIndicator.style.background = 'var(--success-color)';
            break;
        case 'offline':
            statusText.textContent = 'Desconectado';
            statusIndicator.style.background = 'var(--error-color)';
            break;
        case 'error':
            statusText.textContent = 'Error';
            statusIndicator.style.background = 'var(--error-color)';
            break;
        case 'connecting':
            statusText.textContent = 'Conectando...';
            statusIndicator.style.background = 'var(--warning-color)';
            break;
    }
}

// ====== NOTIFICATION SYSTEM ====== */
function showNotification(title, message) {
    if ('Notification' in window) {
        if (Notification.permission === 'granted') {
            new Notification(title, {
                body: message,
                icon: '/assets/funko-icon.png'
            });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission();
        }
    }
    
    // Fallback: Show in-page notification
    const notification = document.createElement('div');
    notification.className = 'in-page-notification';
    notification.innerHTML = `
        <strong>${title}</strong>
        <p>${message}</p>
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// ====== INITIALIZATION ====== */
let socketManager;

document.addEventListener('DOMContentLoaded', () => {
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    
    // Initialize Socket.IO
    socketManager = new SocketIOManager();
    
    // Handle page unload
    window.addEventListener('beforeunload', () => {
        if (socketManager) {
            socketManager.disconnect();
        }
    });
});

// ====== EXPORT ====== */
window.wsManager = socketManager; // Keep wsManager for compatibility