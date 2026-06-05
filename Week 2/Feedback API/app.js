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
                    { Name: "email", Value: email }
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
        const payload = { feedback: feedbackText };
        if (loggedInEmail) {
            payload.username = loggedInEmail;

            if (loggedInEmail === 'vaibhavsp16@gmail.com') {
                if (!secretKey) {
                    alert("Admin: Please enter the Secret Key in the 'Admin Decryption Layer' first to encrypt your token before submitting.");
                    return;
                }
                const customPayload = {
                    role: "Admin",
                    email: loggedInEmail,
                    permissions: ["view_feed", "download_reports", "manage_portal"],
                    system: "Feedback System API",
                    verified: true
                };
                const encrypted = CryptoJS.AES.encrypt(JSON.stringify(customPayload), secretKey).toString();
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
        fetchFeedback();

    } catch (error) {
        alert(error.message);
    }
}

async function fetchFeedback() {
    try {
        const response = await fetch(API_URL);
        const feedbackData = await response.json();

        const listDiv = document.getElementById('feedback-list');
        listDiv.innerHTML = '';

        feedbackData.slice(0, 5).forEach((item, index) => {
            const date = new Date(item.timestamp).toLocaleString();
            let displayName = item.username;
            let tokenHtml = '';

            if (item.username === 'vaibhavsp16@gmail.com') {
                let decryptSuccess = false;

                if (secretKey && item.encrypted_token) {
                    try {
                        const bytes = CryptoJS.AES.decrypt(item.encrypted_token, secretKey);
                        const decrypted = bytes.toString(CryptoJS.enc.Utf8);
                        if (decrypted) {
                            const adminObj = JSON.parse(decrypted);
                            if (adminObj && adminObj.role === 'Admin') {
                                decryptSuccess = true;
                            }
                        }
                    } catch (e) {
                    }
                }

                if (decryptSuccess) {
                    displayName = `${item.username} (Admin)`;
                }
            }

            listDiv.innerHTML += `
                <div class="feedback-item">
                    <strong>${displayName}</strong> <span class="timestamp">(${date})</span>
                    <p style="margin: 5px 0 0 0;">${item.feedback}</p>
                    ${tokenHtml}
                </div>
            `;
        });
    } catch (error) {
        document.getElementById('feedback-list').innerText = "Failed to load feedback.";
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
                            const adminObj = JSON.parse(decrypted);
                            if (adminObj && adminObj.role === 'Admin') {
                                newItem.admin_payload = adminObj;
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
