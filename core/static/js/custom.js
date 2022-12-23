const POSSIBLE_REDIRECTS = ["subscriptions/fetch?op=migrate", "login", "", "subscriptions/fetch?op=unsubscribe", "subscriptions/unsubscribe", "playlists/fetch"].forEach((url) => { encodeURIComponent(url) })
const login = (redirect) => {
    var redirectUrl = redirect.toString().trim().toLowerCase()
    let encodedRedirectUrl = encodeURIComponent(redirectUrl)
    if ((typeof(encodedRedirectUrl) != typeof("string")) && (POSSIBLE_REDIRECTS.includes(encodedRedirectUrl))) throw Error("Invalid call!")
    if (encodedRedirectUrl === "login") encodedRedirectUrl = ""
    var access_token = window.sessionStorage.getItem("access_token")
        //Check if there is an access token  in session storage
    if (access_token === null) {
        return document.location.href = "/login?redirect=" + encodedRedirectUrl
    }

    return document.location.href = "/login?logged_in=true&redirect=" + encodedRedirectUrl

}


const logout = () => {
    init = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    }
    access_token = window.sessionStorage.getItem("access_token");
    fetch("/logout").then((response) => {
        if (response.status == 200) {
            window.sessionStorage.removeItem("access_token")
            document.location.href = ("/")
        }
    }).catch((reject) => { throw reject })
}