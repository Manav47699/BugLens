document.addEventListener('DOMContentLoaded', () => {
    // DOM Node Queries
    const cursor = document.querySelector('.custom-cursor');
    const directoryPicker = document.getElementById('directoryPicker');
    const dropzone = document.getElementById('dropzone');
    const uploadStatus = document.getElementById('uploadStatus');
    const startDebugBtn = document.getElementById('startDebugBtn');
    const terminalSection = document.getElementById('terminalSection');
    const terminalOutput = document.getElementById('terminalOutput');
    const summarySection = document.getElementById('summarySection');

    // Report Detail Output Fields
    const reportProblem = document.getElementById('reportProblem');
    const reportFile = document.getElementById('reportFile');
    const reportCause = document.getElementById('reportCause');
    const reportExplanation = document.getElementById('reportExplanation');
    const reportFix = document.getElementById('reportFix');
    const copyCodeBtn = document.getElementById('copyCodeBtn');

    let selectedPathName = "";

    // 1. Fluid Custom Trailing Mouse Motion Handling
    document.addEventListener('mousemove', (e) => {
        cursor.style.left = `${e.clientX}px`;
        cursor.style.top = `${e.clientY}px`;
    });

    // Handle hovering states to match premium interfaces
    const interactiveElements = document.querySelectorAll('button, select, input, .dropzone-area, .btn-copy');
    interactiveElements.forEach(el => {
        el.addEventListener('mouseenter', () => cursor.classList.add('hovering'));
        el.addEventListener('mouseleave', () => cursor.classList.remove('hovering'));
    });

    // 2. Folder Dropzone/Selection Engine Implementation
    directoryPicker.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            // Extract baseline directory path from native file webkitRelativePath
            const rootDirName = files[0].webkitRelativePath.split('/')[0];
            selectedPathName = rootDirName;
            uploadStatus.textContent = `/${rootDirName} (${files.length} files selected)`;
            startDebugBtn.removeAttribute('disabled');
            logToTerminal(`System workspace localized to structure: /${rootDirName}`, 'success');
        }
    });

    // Drag and Drop Visual Modifiers
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
        }, false);
    });

    // 3. Terminal Output Logger Engine
    function logToTerminal(text, type = 'exec') {
        const line = document.createElement('div');
        line.className = `terminal-line status-${type}`;
        
        const timestamp = new Date().toLocaleTimeString([], { hour12: false });
        line.innerHTML = `[${timestamp}] <span class="log-text">${text}</span>`;
        
        terminalOutput.appendChild(line);
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }

    // 4. Mock Diagnostic Orchestration Pipeline Strategy
    startDebugBtn.addEventListener('click', async () => {
        // Reset and show console panel UI layout state
        terminalOutput.innerHTML = '';
        terminalSection.classList.remove('hidden');
        summarySection.classList.add('hidden');
        startDebugBtn.setAttribute('disabled', 'true');

        // Step-by-Step Simulation Flow
        logToTerminal(`Initializing orchestration sequence for environment: HTML5 Core`, 'exec');
        
        await delay(1000);
        logToTerminal(`Bootstrapping secure local workspace isolation sandbox...`, 'exec');
        
        await delay(1200);
        logToTerminal(`Running Automated Crawl Agent via Simulated Document Traversal...`, 'exec');
        logToTerminal(`DOM Scan Complete: Located interactive node elements: [button#submit-btn]`, 'success');
        
        await delay(1500);
        logToTerminal(`Executing execution script simulation thread on: button#submit-btn`, 'exec');
        
        await delay(800);
        logToTerminal(`CRITICAL EXCEPTION DETECTED: Runtime processing termination event forced`, 'alert');
        logToTerminal(`Uncaught TypeError: Cannot read properties of undefined (reading 'name')`, 'alert');
        
        await delay(1000);
        logToTerminal(`Packaging telemetry data payload structure. Accessing local Ollama node (qwen2.5:0.5b)...`, 'exec');

        // 5. Native Communication Fetch Layer directly targetting Python Core
        try {
            const response = await fetch('http://127.0.0.1:8000/debug', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project: selectedPathName })
            });

            if (!response.ok) throw new Error("Backend connection error occurred");
            
            const data = await response.json();
            
            logToTerminal(`Telemetry pipeline response processed successfully from local LLM.`, 'success');
            
            // Populating UI Elements securely from returned context
            reportProblem.textContent = data.problem || "Login Form Triggering Uncaught Runtime Crash";
            reportFile.textContent = data.file || "target_project/index.html";
            reportCause.textContent = data.cause || "Expression attempts invocation of variables nested inside uninstantiated objects.";
            reportExplanation.textContent = data.explanation || "The element listener assumes an existing initialized layout parameters layer configuration. When evaluations occur before responses load, standard components fail properties checks.";
            reportFix.textContent = data.fix || `// Safeguard object property invocation\nsubmitButton.addEventListener('click', () => {\n    if (typeof user !== 'undefined' && user.name) {\n        console.log(user.name);\n    } else {\n        console.error("Context processing halted: User dataset missing initialization.");\n    }\n});`;

            // Display Report Layer
            summarySection.classList.remove('hidden');
            window.scrollTo({ top: summarySection.offsetTop - 40, behavior: 'smooth' });

        } catch (error) {
            logToTerminal(`Telemetry pipeline processing failure: ${error.message}`, 'alert');
            logToTerminal(`Defaulting to architectural prototype mockup report data models...`, 'exec');
            
            // Elegant Failback Rendering Strategy if local python agent isn't active yet
            await delay(1000);
            renderMockupDataFallback();
        } finally {
            startDebugBtn.removeAttribute('disabled');
        }
    });

    // Secondary UI Helper Utilities
    const delay = (ms) => new Promise(res => setTimeout(res, ms));

    function renderMockupDataFallback() {
        reportProblem.textContent = "Click Action Triggers Uncaught Reference Crash";
        reportFile.textContent = "target_project/index.html";
        reportCause.textContent = "System script evaluates properties from completely unassigned object targets (user.name).";
        reportExplanation.textContent = "The event dispatcher execution thread invokes parameter references directly on a variable container that has not been structurally instantiated or verified inside the script scopes.";
        reportFix.textContent = `// Resolving context invocation via baseline checks\nconst user = window.currentUser || { name: "Guest Session" };\n\nbtn.addEventListener('click', () => {\n    // Fixed property execution route safely inside block scope\n    console.log(user.name);\n});`;
        summarySection.classList.remove('hidden');
    }

    copyCodeBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(reportFix.textContent);
        copyCodeBtn.textContent = "Copied!";
        setTimeout(() => copyCodeBtn.textContent = "Copy", 2000);
    });
});