const POSSIBLE_REDIRECTS = ["subscriptions/fetch", "login", "", "subscriptions/post"]
const login = (redirect) => {
    var redirect_url = redirect.toString().trim().toLowerCase()
        //redirect validation. 
    if ((typeof(redirect_url) != typeof("string")) && (POSSIBLE_REDIRECTS.includes(redirect_url))) throw Error("Invalid call!")
    if (redirect_url === "login") redirect_url = ""
    var access_token = window.sessionStorage.getItem("access_token")
        //Check if there is an access token  in session storage
    if (access_token === null) {
        return document.location.href = "/login?redirect=" + redirect_url
    }

    return document.location.href = "/login?logged_in=true&redirect=" + redirect_url

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