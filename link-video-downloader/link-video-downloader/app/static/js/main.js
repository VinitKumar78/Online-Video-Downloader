document.getElementById('download-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const urlInput = document.getElementById('video-url');
    const fetchBtn = document.getElementById('fetch-btn');
    const errorBanner = document.getElementById('error-banner');
    const errorText = document.getElementById('error-text');
    
    const resultCard = document.getElementById('result-card');
    const resultTitle = document.getElementById('result-title');
    const resultUploader = document.getElementById('result-uploader');
    const downloadBtn = document.getElementById('download-btn');
    
    errorBanner.classList.add('hidden');
    resultCard.classList.add('hidden');
    fetchBtn.disabled = true;
    fetchBtn.style.opacity = '0.7';
    fetchBtn.innerText = "Processing...";
    
    const url = urlInput.value.trim();
    
    try {
        const response = await fetch('/api/info', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            throw new Error("Server returned an invalid HTML response. Please check your backend terminal logs.");
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            let rawError = data.error || "An unexpected issue occurred while extracting file details.";
            let cleanMsg = rawError.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
            throw new Error(cleanMsg);
        }
        
        resultTitle.innerText = data.title || "Target File Container";
        resultUploader.innerText = data.uploader || "Direct Download Link";
        
        downloadBtn.onclick = async () => {
            downloadBtn.disabled = true;
            downloadBtn.innerText = "Initializing Download Job...";
            
            try {
                const dlResponse = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url, height: 0 })
                });
                const dlData = await dlResponse.json();
                
                if (dlData.job_id) {
                    downloadBtn.innerText = "Downloading Background File Stream...";
                    checkDownloadStatus(dlData.job_id, downloadBtn);
                } else {
                    throw new Error(dlData.error || "Could not spin up download worker thread.");
                }
            } catch (dlErr) {
                alert(dlErr.message);
                downloadBtn.disabled = false;
                downloadBtn.innerText = "Start Secure Download";
            }
        };

        resultCard.classList.remove('hidden');
        
    } catch (err) {
        errorText.innerText = err.message;
        errorBanner.classList.remove('hidden');
    } finally {
        fetchBtn.disabled = false;
        fetchBtn.style.opacity = '1';
        fetchBtn.innerText = "Fetch Video";
    }
});

async function checkDownloadStatus(jobId, actionButton) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/api/status/${jobId}`);
            const statusData = await res.json();
            
            let rawStatus = "";
            if (statusData.status) {
                rawStatus = (typeof statusData.status === 'object' && statusData.status.name)
                    ? String(statusData.status.name).toUpperCase()
                    : String(statusData.status).toUpperCase();
            }

            if (rawStatus === 'DONE' || rawStatus === 'COMPLETED' || statusData.progress === '100%') {
                clearInterval(interval);
                actionButton.innerText = "File Ready! Initializing Download...";
                
                // Triggers native browser download directly without opening any external tab
                window.location.href = `/api/file/${jobId}`;
                
                setTimeout(() => {
                    actionButton.disabled = false;
                    actionButton.innerText = "Start Secure Download";
                }, 3000);
            } else if (rawStatus === 'ERROR' || rawStatus === 'FAILED') {
                clearInterval(interval);
                alert("Download Job Failure: " + (statusData.error || "Unknown system stream error"));
                actionButton.disabled = false;
                actionButton.innerText = "Start Secure Download";
            } else if (statusData.progress) {
                actionButton.innerText = `Downloading: ${statusData.progress}`;
            } else {
                actionButton.innerText = "Downloading: Streaming...";
            }
        } catch (err) {
            console.error("Status check loop tracing failed:", err);
        }
    }, 1500);
}