document.addEventListener('DOMContentLoaded', () => {
    const gardenForm = document.getElementById('gardenForm');
    const imageAnalysisResultDiv = document.getElementById('imageAnalysisResult');
    const gardenAdviceResultDiv = document.getElementById('gardenAdviceResult');
    const svgPlanContainer = document.getElementById('svgPlanContainer');
    const resultsContainer = document.getElementById('resultsContainer');
    const loadingDiv = document.getElementById('loading');
    const timerSpan = document.getElementById('timer');
    const errorResultDiv = document.getElementById('errorResult');
    const backendApiUrl = 'https://DIN-EXTERNT-HOSTADE-BACKEND-URL.com/get_advice'; // <-- VIKTIGT: ÄNDRA DENNA!

    // ... (imageUpload event listener som tidigare) ...

    gardenForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        clearResultsAndErrors(); // Funktion för att rensa tidigare resultat/fel
        loadingDiv.style.display = 'block';
        let timerInterval;
        let seconds = 0;

        timerInterval = setInterval(() => {
            seconds++;
            timerSpan.textContent = seconds;
        }, 1000);

        const formData = new FormData(gardenForm);

        try {
            const response = await fetch(backendApiUrl, { // Använd konfigurerad URL
                method: 'POST',
                body: formData,
            });

            // ... (timer-rensning och loadingDiv-döljning) ...
            clearInterval(timerInterval);
            loadingDiv.style.display = 'none';


            if (!response.ok) {
                let errorDetail = `Servern svarade med status ${response.status}.`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (e) {
                    // Ignorera om svaret inte är JSON, använd den generiska statusen
                }
                throw new Error(errorDetail);
            }

            const data = await response.json();
            displayResults(data); // Funktion för att visa resultat

        } catch (error) {
            clearInterval(timerInterval);
            loadingDiv.style.display = 'none';
            console.error('Fel vid API-anrop:', error);
            errorResultDiv.textContent = 'Ett fel uppstod när råd skulle hämtas: ' + error.message;
            errorResultDiv.style.display = 'block';
        }
    });

    function displayResults(data) {
        if (data.image_analysis_text && data.image_analysis_text !== "Ingen bildanalys utförd (ingen bild skickad).") {
            imageAnalysisResultDiv.textContent = data.image_analysis_text;
            imageAnalysisSection.style.display = 'block';
        } else {
            imageAnalysisSection.style.display = 'none';
        }
        gardenAdviceResultDiv.textContent = data.text_advice;
        svgPlanContainer.innerHTML = data.svg_plan;
        resultsContainer.style.display = 'block';
    }

    function clearResultsAndErrors() {
        resultsContainer.style.display = 'none';
        imageAnalysisSection.style.display = 'none';
        errorResultDiv.style.display = 'none';
        errorResultDiv.textContent = ''; // Rensa felmeddelande
        // ... (rensa andra resultatfält) ...
         if (timerInterval) clearInterval(timerInterval);
         timerSpan.textContent = '0';
    }
});