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
        
        downloadBtn.onclick = () => {
            downloadBtn.disabled = true;
            downloadBtn.innerText = "Initiating Browser Download...";
            
            // Route directly to our backend stream handler which pipes data straight into the browser tray
            window.location.href = `/api/stream-download?url=${encodeURIComponent(url)}`;
            
            setTimeout(() => {
                downloadBtn.disabled = false;
                downloadBtn.innerText = "Start Secure Download";
            }, 3000);
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
