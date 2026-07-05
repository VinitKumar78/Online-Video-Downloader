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
        
        // DYNAMIC HANDSHAKE TRIGGER OVERRIDE
        downloadBtn.onclick = async () => {
            if (url.includes("diskwala.com")) {
                downloadBtn.innerText = "Downloading...";
                downloadBtn.disabled = true;

                // Extract the exact file ID string safely using JS path splits
                const urlParts = url.split("/app/");
                let fileId = urlParts[urlParts.length - 1];
                if (fileId && fileId.includes("?")) {
                    fileId = fileId.split("?")[0];
                }
                
                if (!fileId) {
                    alert("Could not parse a valid file ID from this URL.");
                    downloadBtn.disabled = false;
                    downloadBtn.innerText = "Start Secure Download";
                    return;
                }

                // Point directly to Diskwala's download API route
                const directCdnUrl = `https://www.diskwala.com/api/v1/file/download/${fileId}`;
                
                // Create an invisible iframe to download the stream silently inside the browser sandbox
                let hiddenFrame = document.getElementById('silent-download-frame');
                if (!hiddenFrame) {
                    hiddenFrame = document.createElement('iframe');
                    hiddenFrame.id = 'silent-download-frame';
                    hiddenFrame.style.display = 'none';
                    document.body.appendChild(hiddenFrame);
                }
                
                // Load the direct download target inside the hidden frame
                hiddenFrame.src = directCdnUrl;

                setTimeout(() => {
                    downloadBtn.disabled = false;
                    downloadBtn.innerText = "Start Secure Download";
                }, 4000);
            } else {
                // Standard server-side queue worker for streaming media platforms (YouTube, Instagram)
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