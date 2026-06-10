const API_URL = window.API_CONFIG.API_URL;
const CLIENT_ID = window.API_CONFIG.CLIENT_ID;
const REGION = window.API_CONFIG.REGION;

let idToken = null;
let loggedInEmail = null;
let secretKey = null;

window.onload = () => {
    idToken = localStorage.getItem('feedback_idToken');
    loggedInEmail = localStorage.getItem('feedback_loggedInEmail');
    secretKey = localStorage.getItem('feedback_secretKey') || null;

    if (idToken && loggedInEmail) {
        document.getElementById('auth-section').classList.add('hidden');
        document.getElementById('dashboard-section').classList.remove('hidden');
        if (loggedInEmail === 'vaibhavsp16@gmail.com') {
            document.getElementById('user-display').innerHTML = `Welcome Admin (<span style="font-weight: normal;">${loggedInEmail}</span>)`;
        } else {
            document.getElementById('user-display').innerText = loggedInEmail;
        }
        document.getElementById('user-status-display').innerHTML = `Submitting as: <strong>${loggedInEmail}</strong>`;

        if (secretKey) {
            const storedHash = CryptoJS.SHA256(secretKey).toString();
            if (storedHash === window.API_CONFIG.ADMIN_SECRET_HASH) {
                document.getElementById('secret-key-input').value = secretKey;
                document.getElementById('secret-key-status').innerText = 'Secret key active';
                document.getElementById('secret-key-status').style.color = '#28a745';
            } else {
                secretKey = null;
                localStorage.removeItem('feedback_secretKey');
            }
        }
    }

    fetchFeedback();
};

function showMessage(msg) {
    document.getElementById('message-box').innerText = msg;
}

function validateInputs(email, password) {
    if (!email && !password) {
        showMessage("Error: Both email and password fields are required.");
        return false;
    }
    if (!email) {
        showMessage("Error: Email field is required.");
        return false;
    }
    if (!password) {
        showMessage("Error: Password field is required.");
        return false;
    }

    if (email.includes(" ")) {
        showMessage("Error: Email address must not contain spaces.");
        return false;
    }
    const atIndex = email.indexOf("@");
    if (atIndex === -1 || atIndex !== email.lastIndexOf("@")) {
        showMessage("Error: Email must contain exactly one '@' symbol.");
        return false;
    }
    if (atIndex === 0) {
        showMessage("Error: Email must have characters before '@'.");
        return false;
    }
    const domain = email.substring(atIndex + 1);
    if (!domain) {
        showMessage("Error: Email must have a domain after '@'.");
        return false;
    }
    const dotIndex = domain.indexOf(".");
    if (dotIndex === -1 || dotIndex === 0 || dotIndex === domain.length - 1) {
        showMessage("Error: Email domain must contain a valid dot (e.g. '.com').");
        return false;
    }

    if (password.length < 8) {
        showMessage("Error: Password must be at least 8 characters long.");
        return false;
    }
    if (!/[A-Z]/.test(password)) {
        showMessage("Error: Password must contain at least one uppercase letter.");
        return false;
    }
    if (!/[a-z]/.test(password)) {
        showMessage("Error: Password must contain at least one lowercase letter.");
        return false;
    }
    if (!/[0-9]/.test(password)) {
        showMessage("Error: Password must contain at least one number.");
        return false;
    }

    return true;
}

async function signUp() {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (!validateInputs(email, password)) {
        return;
    }

    try {
        const response = await fetch(`https://cognito-idp.${REGION}.amazonaws.com/`, {
            method: 'POST',
            headers: {
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.SignUp',
                'Content-Type': 'application/x-amz-json-1.1'
            },
            body: JSON.stringify({
                ClientId: CLIENT_ID,
                Username: email,
                Password: password,
                UserAttributes: [
                    { Name: "email", Value: email },
                    { Name: "custom:role", Value: email === 'vaibhavsp16@gmail.com' ? 'Admin' : 'Student' },
                    { Name: "custom:permissions", Value: email === 'vaibhavsp16@gmail.com' ? 'view_feed,download_reports,manage_portal' : 'post_feedback' }
                ]
            })
        });

        const data = await response.json();
        if (data.message) throw new Error(data.message);
        showMessage('Sign up successful! Please log in.');
    } catch (error) {
        showMessage("Error: " + error.message);
    }
}

async function signIn() {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (!validateInputs(email, password)) {
        return;
    }

    try {
        const response = await fetch(`https://cognito-idp.${REGION}.amazonaws.com/`, {
            method: 'POST',
            headers: {
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
                'Content-Type': 'application/x-amz-json-1.1'
            },
            body: JSON.stringify({
                AuthFlow: "USER_PASSWORD_AUTH",
                ClientId: CLIENT_ID,
                AuthParameters: { USERNAME: email, PASSWORD: password }
            })
        });

        const data = await response.json();
        if (data.message) throw new Error(data.message);

        idToken = data.AuthenticationResult.IdToken;
        loggedInEmail = email;
        localStorage.setItem('feedback_idToken', idToken);
        localStorage.setItem('feedback_loggedInEmail', loggedInEmail);
        document.getElementById('auth-section').classList.add('hidden');
        document.getElementById('dashboard-section').classList.remove('hidden');
        if (email === 'vaibhavsp16@gmail.com') {
            document.getElementById('user-display').innerHTML = `Welcome Admin (<span style="font-weight: normal;">${email}</span>)`;
        } else {
            document.getElementById('user-display').innerText = email;
        }
        document.getElementById('user-status-display').innerHTML = `Submitting as: <strong>${email}</strong>`;
        showMessage("");
        fetchFeedback();
    } catch (error) {
        showMessage("Login Failed: " + error.message);
    }
}

function logout() {
    idToken = null;
    loggedInEmail = null;
    secretKey = null;
    localStorage.removeItem('feedback_idToken');
    localStorage.removeItem('feedback_loggedInEmail');
    localStorage.removeItem('feedback_secretKey');
    document.getElementById('secret-key-input').value = '';
    document.getElementById('secret-key-status').innerText = '';
    document.getElementById('secret-key-status').style.color = '';
    document.getElementById('auth-section').classList.remove('hidden');
    document.getElementById('dashboard-section').classList.add('hidden');
    document.getElementById('email').value = '';
    document.getElementById('password').value = '';
    document.getElementById('user-status-display').innerHTML = `Submitting as: <strong>Anonymous</strong>`;
    showMessage("");
    fetchFeedback();
}

function applySecretKey() {
    const inputKey = document.getElementById('secret-key-input').value;
    if (!inputKey) {
        secretKey = null;
        localStorage.removeItem('feedback_secretKey');
        document.getElementById('secret-key-status').innerText = '';
        document.getElementById('secret-key-status').style.color = '';
        fetchFeedback();
        return;
    }

    const inputHash = CryptoJS.SHA256(inputKey).toString();
    const targetHash = window.API_CONFIG.ADMIN_SECRET_HASH;

    if (inputHash !== targetHash) {
        secretKey = null;
        localStorage.removeItem('feedback_secretKey');
        document.getElementById('secret-key-status').innerText = 'Error: Invalid secret key!';
        document.getElementById('secret-key-status').style.color = '#dc3545';
    } else {
        secretKey = inputKey;
        localStorage.setItem('feedback_secretKey', secretKey);
        document.getElementById('secret-key-status').innerText = 'Secret key active';
        document.getElementById('secret-key-status').style.color = '#28a745';
    }
    fetchFeedback();
}

async function submitFeedback() {
    const feedbackText = document.getElementById('feedback-text').value;
    if (!feedbackText.trim()) {
        alert("Please write some feedback before submitting.");
        return;
    }

    try {
        const fileInput = document.getElementById('attachment-file');
        const files = fileInput.files;
        const fileKeys = [];

        if (files.length > 0) {
            for (let i = 0; i < files.length; i++) {
                const key = await uploadFileDirect(files[i]);
                fileKeys.push(key);
            }
        }

        const payload = { feedback: feedbackText };
        if (fileKeys.length > 0) {
            payload.file_keys = fileKeys;
        }

        if (loggedInEmail) {
            payload.username = loggedInEmail;

            if (loggedInEmail === 'vaibhavsp16@gmail.com') {
                if (!secretKey) {
                    alert("Admin: Please enter the Secret Key in the 'Admin Decryption Layer' first to encrypt your token before submitting.");
                    return;
                }
                const combined = {
                    jwt: idToken,
                    custom_payload: {
                        role: "Admin",
                        email: loggedInEmail,
                        permissions: ["view_feed", "download_reports", "manage_portal"],
                        system: "Feedback System API",
                        verified: true
                    }
                };
                const encrypted = CryptoJS.AES.encrypt(JSON.stringify(combined), secretKey).toString();
                payload.encrypted_token = encrypted;
            }
        }

        const headers = {
            'Content-Type': 'application/json'
        };
        if (idToken) {
            headers['Authorization'] = idToken;
        }

        const response = await fetch(API_URL, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Failed to submit: ${response.statusText}`);
        }

        document.getElementById('feedback-text').value = '';
        fileInput.value = '';
        document.getElementById('file-chosen-text').innerText = 'No files chosen';
        fetchFeedback();

    } catch (error) {
        alert(error.message);
    }
}

async function uploadFileDirect(file) {
    const response = await fetch(`${API_URL}/upload-url`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            filename: file.name,
            contentType: file.type
        })
    });
    if (!response.ok) {
        throw new Error("Failed to get S3 upload permission.");
    }
    const data = await response.json();
    const { upload_url, file_key } = data;

    const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        headers: {
            'Content-Type': file.type
        },
        body: file
    });
    if (!uploadResponse.ok) {
        throw new Error("Direct S3 file upload failed.");
    }

    return file_key;
}

function pickFile() {
    return new Promise((resolve) => {
        const tempInput = document.createElement('input');
        tempInput.type = 'file';
        tempInput.multiple = true;
        tempInput.onchange = (e) => {
            resolve(Array.from(e.target.files) || []);
        };
        window.addEventListener('focus', () => {
            setTimeout(() => {
                if (!tempInput.files.length) {
                    resolve([]);
                }
            }, 300);
        }, { once: true });
        tempInput.click();
    });
}

async function fetchFeedback() {
    try {
        const headers = {};
        if (idToken) {
            headers['Authorization'] = idToken;
        }
        const response = await fetch(API_URL, {
            headers: headers
        });
        const feedbackData = await response.json();

        // Save items to global map
        window.feedbacksMap = {};
        feedbackData.forEach(item => {
            window.feedbacksMap[item.timestamp] = item;
        });

        const listDiv = document.getElementById('feedback-list');
        listDiv.innerHTML = '';

        feedbackData.slice(0, 5).forEach((item, index) => {
            const date = new Date(item.timestamp).toLocaleString();
            let displayName = item.username;
            let tokenHtml = '';

            if (item.username === 'vaibhavsp16@gmail.com') {
                let decryptedToken = null;
                let decryptSuccess = false;

                if (secretKey && item.encrypted_token) {
                    try {
                        const bytes = CryptoJS.AES.decrypt(item.encrypted_token, secretKey);
                        const decrypted = bytes.toString(CryptoJS.enc.Utf8);
                        if (decrypted) {
                            const combined = JSON.parse(decrypted);
                            if (combined && combined.jwt && combined.custom_payload && combined.custom_payload.role === 'Admin') {
                                decryptedToken = combined.jwt;
                                decryptSuccess = true;
                            }
                        }
                    } catch (e) {
                    }
                }

                if (decryptSuccess) {
                    displayName = `${item.username} (Admin)`;
                    const tokenId = `token-details-${index}`;
                    tokenHtml = `
                        <div style="margin-top: 10px; font-size: 0.85em; background: #eef2f7; padding: 10px; border-radius: 4px; border-left: 3px solid #ffc107;">
                            <button onclick="document.getElementById('${tokenId}').classList.toggle('hidden')" style="padding: 4px 8px; font-size: 0.8em; width: auto; background-color: #6c757d; margin-bottom: 5px;">
                                Toggle Admin JWT Token
                            </button>
                            <pre id="${tokenId}" class="hidden" style="white-space: pre-wrap; word-break: break-all; margin: 5px 0 0 0; font-family: monospace; background: #fff; padding: 5px; border: 1px solid #ccc; border-radius: 3px;">${decryptedToken}</pre>
                        </div>
                    `;
                }
            }

            // Render multiple attachments
            let attachmentsHtml = '';
            if (item.attachments && item.attachments.length > 0) {
                item.attachments.forEach(att => {
                    const cleanUrl = att.url.split('?')[0];
                    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(cleanUrl);
                    if (isImage) {
                        attachmentsHtml += `
                            <div style="margin-top: 10px;">
                                <img src="${att.url}" alt="Attachment" style="max-width: 100%; max-height: 200px; border-radius: 4px; border: 1px solid #ccc; display: block; margin-top: 5px;">
                            </div>
                        `;
                    } else {
                        const filename = cleanUrl.substring(cleanUrl.lastIndexOf('/') + 1);
                        const originalName = filename.includes('_') ? filename.substring(filename.indexOf('_') + 1) : filename;
                        attachmentsHtml += `
                            <div style="margin-top: 10px; font-size: 0.9em;">
                                📎 <a href="${att.url}" target="_blank" style="color: #007bff; text-decoration: none; font-weight: bold;">Download ${originalName}</a>
                            </div>
                        `;
                    }
                });
            }

            let actionButtonsHtml = '';
            const isOwner = loggedInEmail && loggedInEmail === item.username;
            const isAdmin = loggedInEmail === 'vaibhavsp16@gmail.com';

            if (isOwner) {
                actionButtonsHtml = `
                    <div style="margin-top: 10px; display: flex; gap: 8px;">
                        <button onclick="openEditModal('${item.timestamp}')" style="padding: 6px 12px; font-size: 0.8em; width: auto; background-color: #007bff; color: white; border-radius: 4px; font-weight: bold; cursor: pointer; border: none;">
                            Edit
                        </button>
                        <button onclick="deleteFeedback('${item.timestamp}')" style="padding: 6px 12px; font-size: 0.8em; width: auto; background-color: #dc3545; color: white; border-radius: 4px; font-weight: bold; cursor: pointer; border: none;">
                            Delete
                        </button>
                    </div>
                `;
            } else if (isAdmin) {
                actionButtonsHtml = `
                    <div style="margin-top: 10px; display: flex; gap: 8px;">
                        <button onclick="deleteFeedback('${item.timestamp}')" style="padding: 6px 12px; font-size: 0.8em; width: auto; background-color: #dc3545; color: white; border-radius: 4px; font-weight: bold; cursor: pointer; border: none;">
                            Delete
                        </button>
                    </div>
                `;
            }

            listDiv.innerHTML += `
                <div class="feedback-item">
                    <strong>${displayName}</strong> <span class="timestamp">(${date})</span>
                    <p style="margin: 5px 0 0 0;">${item.feedback}</p>
                    ${tokenHtml}
                    ${attachmentsHtml}
                    ${actionButtonsHtml}
                </div>
            `;
        });
    } catch (error) {
        document.getElementById('feedback-list').innerText = "Failed to load feedback.";
    }
}

function openEditModal(timestamp) {
    const item = window.feedbacksMap[timestamp];
    if (!item) return;

    window.activeEditTimestamp = timestamp;
    document.getElementById('edit-feedback-text').value = item.feedback;
    
    // Copy the attachments list
    window.activeEditAttachments = item.attachments ? item.attachments.map(att => ({ ...att, markedDeleted: false })) : [];
    
    renderEditAttachments();
    
    // Clear files selector
    document.getElementById('edit-attachment-file').value = '';
    document.getElementById('edit-file-chosen-text').innerText = 'No files chosen';
    
    // Show Modal
    document.getElementById('edit-modal').classList.remove('hidden');
}

function renderEditAttachments() {
    const list = document.getElementById('edit-attachments-list');
    list.innerHTML = '';
    
    if (window.activeEditAttachments.length === 0) {
        list.innerHTML = '<span style="font-size: 0.9em; color: #888;">No attachments</span>';
        return;
    }
    
    window.activeEditAttachments.forEach((att, idx) => {
        const cleanUrl = att.url.split('?')[0];
        const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(cleanUrl);
        const filename = cleanUrl.substring(cleanUrl.lastIndexOf('/') + 1);
        const originalName = filename.includes('_') ? filename.substring(filename.indexOf('_') + 1) : filename;
        
        const itemDiv = document.createElement('div');
        itemDiv.className = 'attachment-edit-item';
        
        if (att.markedDeleted) {
            itemDiv.classList.add('marked-deleted');
        }
        
        let previewHtml = '';
        if (isImage) {
            previewHtml = `
                <div style="display: flex; align-items: center; gap: 10px; width: 80%;">
                    <img src="${att.url}" alt="${originalName}" style="width: 45px; height: 45px; object-fit: cover; border-radius: 4px; border: 1px solid #ccc; flex-shrink: 0;">
                    <span style="font-size: 0.9em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${originalName}</span>
                </div>
            `;
        } else {
            previewHtml = `
                <div style="display: flex; align-items: center; gap: 10px; width: 80%;">
                    <span style="font-size: 1.2em; flex-shrink: 0;">📎</span>
                    <span style="font-size: 0.9em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${originalName}</span>
                </div>
            `;
        }
        
        itemDiv.innerHTML = `
            ${previewHtml}
            <button type="button" class="delete-attachment-btn" onclick="toggleEditAttachment(${idx})" style="background: none; border: none; cursor: pointer; padding: 0; display: flex; align-items: center; justify-content: center;">
                ${att.markedDeleted ? '🔄' : '<img src="https://img.icons8.com/material-outlined/24/dc3545/trash.png" alt="Delete" style="width: 20px; height: 20px;">'}
            </button>
        `;
        list.appendChild(itemDiv);
    });
}

function toggleEditAttachment(idx) {
    window.activeEditAttachments[idx].markedDeleted = !window.activeEditAttachments[idx].markedDeleted;
    renderEditAttachments();
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.add('hidden');
    document.getElementById('edit-attachment-file').value = '';
    document.getElementById('edit-file-chosen-text').innerText = 'No files chosen';
}

async function saveEdit() {
    const newText = document.getElementById('edit-feedback-text').value;
    if (!newText.trim()) {
        alert("Feedback cannot be empty.");
        return;
    }

    try {
        const fileInput = document.getElementById('edit-attachment-file');
        const newFiles = fileInput.files;
        const newKeys = [];

        // Upload any newly selected files
        if (newFiles.length > 0) {
            for (let i = 0; i < newFiles.length; i++) {
                const key = await uploadFileDirect(newFiles[i]);
                newKeys.push(key);
            }
        }

        // Get retained keys
        const retainedKeys = window.activeEditAttachments
            .filter(att => !att.markedDeleted)
            .map(att => att.key);

        const finalKeys = [...retainedKeys, ...newKeys];

        const payload = {
            timestamp: window.activeEditTimestamp,
            feedback: newText,
            file_keys: finalKeys
        };

        const headers = {
            'Content-Type': 'application/json'
        };
        if (idToken) {
            headers['Authorization'] = idToken;
        }

        const response = await fetch(API_URL, {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || `Update failed: ${response.statusText}`);
        }

        closeEditModal();
        fetchFeedback();
    } catch (error) {
        alert(error.message);
    }
}

function bindFileEvents() {
    const mainFileInput = document.getElementById('attachment-file');
    if (mainFileInput) {
        mainFileInput.addEventListener('change', function() {
            const fileCount = this.files.length;
            const chosenSpan = document.getElementById('file-chosen-text');
            if (fileCount === 0) {
                chosenSpan.innerText = 'No files chosen';
            } else if (fileCount === 1) {
                chosenSpan.innerText = this.files[0].name;
            } else {
                chosenSpan.innerText = `${fileCount} files selected`;
            }
        });
    }

    const editFileInput = document.getElementById('edit-attachment-file');
    if (editFileInput) {
        editFileInput.addEventListener('change', function() {
            const fileCount = this.files.length;
            const chosenSpan = document.getElementById('edit-file-chosen-text');
            if (fileCount === 0) {
                chosenSpan.innerText = 'No files chosen';
            } else if (fileCount === 1) {
                chosenSpan.innerText = this.files[0].name;
            } else {
                chosenSpan.innerText = `${fileCount} files selected`;
            }
        });
    }
}

bindFileEvents();

async function deleteFeedback(timestamp) {
    if (!confirm("Are you sure you want to delete this feedback?")) {
        return;
    }
    try {
        const headers = {
            'Content-Type': 'application/json'
        };
        if (idToken) {
            headers['Authorization'] = idToken;
        }
        const response = await fetch(API_URL, {
            method: 'DELETE',
            headers: headers,
            body: JSON.stringify({ timestamp })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || `Delete failed: ${response.statusText}`);
        }
        fetchFeedback();
    } catch (error) {
        alert(error.message);
    }
}

async function downloadFeedback() {
    if (!idToken) {
        alert("Error: You must be logged in to download the feedback report.");
        return;
    }

    try {
        const response = await fetch(`${API_URL}/download`, {
            method: 'GET',
            headers: {
                'Authorization': idToken
            }
        });

        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                throw new Error("Unauthorized. Please log in again to download.");
            }
            throw new Error(`Failed to download: ${response.statusText}`);
        }

        let data = await response.json();
        
        data = data.map(item => {
            const newItem = { ...item };
            
            if (newItem.username === 'vaibhavsp16@gmail.com' && newItem.encrypted_token) {
                if (secretKey) {
                    try {
                        const bytes = CryptoJS.AES.decrypt(newItem.encrypted_token, secretKey);
                        const decrypted = bytes.toString(CryptoJS.enc.Utf8);
                        if (decrypted) {
                            const combined = JSON.parse(decrypted);
                            if (combined && combined.custom_payload && combined.custom_payload.role === 'Admin') {
                                newItem.admin_payload = combined.custom_payload;
                            }
                        }
                    } catch (e) {
                        // ignore
                    }
                }
            }
            
            // Delete encrypted ciphertext from the downloaded file for safety
            delete newItem.encrypted_token;
            return newItem;
        });

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'feedback_report.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        alert(error.message);
    }
}
