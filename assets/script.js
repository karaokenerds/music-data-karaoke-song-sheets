const notLoading = () => {
    document.getElementById("loadingSpinner").style.display = "none";

    let buttons = document.getElementsByTagName("button");
    for (i = 0; i < buttons.length; i++) {
        buttons[i].disabled = false;
    }
}

const loading = () => {
    document.getElementById("loadingSpinner").style.display = "inline-block";

    let buttons = document.getElementsByTagName("button");
    for (i = 0; i < buttons.length; i++) {
        buttons[i].disabled = true;
    }
}

document.getElementById("spotifyAuthButton").onclick = function () {
    window.location.href = "/authenticate/spotify";
};

document.getElementById("lastfmAuthButton").onclick = function () {
    let lastfmUsername = document.getElementById("lastfmUsername").value;
    if (lastfmUsername == "") {
        alert("Please enter your last.fm username to proceed")
    } else {
        window.location.href = "/authenticate/lastfm?username=" + lastfmUsername;
    }
};

const googleAuthButton = document.getElementById("googleAuthButton");
googleAuthButton.addEventListener("click", () => {
    window.location.href = "/authorize_google";
});

const clearSessionButton = document.getElementById("clearSessionButton");
clearSessionButton.addEventListener("click", () => {
    document.cookie = "session= ; expires = Thu, 01 Jan 1970 00:00:00 GMT"
    sessionStorage.clear();
    window.location.href = "/reset";
});

const buildSheetButton = document.getElementById("buildSheetButton");
buildSheetButton.addEventListener("click", async () => {
    loading();

    try {
        let includeZeroScoreSongs = document.getElementById("includeZeroScoreSongs").checked;
        // Call the /generate_sheet route
        const response = await fetch("/generate_sheet?includeZeroScoreSongs=" + includeZeroScoreSongs);
        if (response.ok) {
            const sheetUrl = await response.text();

            const sheetLink = document.getElementById("sheetLink");
            sheetLink.querySelector("a").href = sheetUrl;
            sheetLink.style.display = "block";

            notLoading();
        } else {
            const errorBody = await response.text();
            throw new Error(errorBody);
        }
    } catch (errorBody) {
        notLoading();
        document.getElementById("errorsModaliFrame").srcdoc = errorBody;
        $('#errorsModal').modal();
        console.error("Error:", errorBody);
    }
});