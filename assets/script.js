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

async function appleMusicAuth() {
    let music = MusicKit.getInstance();
    const music_user_token = await music.authorize()

    console.log("Apple MusicKit JS authorized");

    try {
        console.log("POSTing music_user_token to /authorize/applemusic_token - " + music_user_token);
        const response = await fetch('/authorize/applemusic_token', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ "music_user_token": music_user_token })
        });

        if (response.ok) {
            appleIDAuthURL = await response.text();
            console.log("Redirecting browser to Apple ID Auth URL from response: " + appleIDAuthURL)
            window.location.href = appleIDAuthURL;
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
}

document.getElementById("applemusicAuthButton").onclick = appleMusicAuth;

document.getElementById("youtubeAuthButton").onclick = function () {
    window.location.href = "/authorize_youtube";
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

const openSheetButton = document.getElementById("openSheetButton");
const buildSheetButton = document.getElementById("buildSheetButton");

async function buildSheetAction() {
    loading();

    try {
        let includeZeroScoreSongs = document.getElementById("includeZeroScoreSongs").checked;
        // Call the /generate_sheet route
        const response = await fetch("/generate_sheet?includeZeroScoreSongs=" + includeZeroScoreSongs);
        if (response.ok) {
            karaokeSheetURL = await response.text();
            openSheetButton.style.display = "inline-block";

            buildSheetButton.classList.remove('btn-primary');
            buildSheetButton.classList.add('btn-success');
            buildSheetButton.classList.add('disabled');
            buildSheetButton.disabled = true;
            buildSheetButton.removeEventListener("click", buildSheetAction);

            notLoading();
            window.open(karaokeSheetURL, '_blank');
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
}

buildSheetButton.addEventListener("click", buildSheetAction);
