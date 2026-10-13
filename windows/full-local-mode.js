// Windows Music Lab full port: no outbound cloud requests or credentials.
(function () {
  "use strict";
  window.WINDOWS_FULL_PORT = {localOnly: true};
  function permitted(value) {
    var url = new URL(typeof value === "string" ? value : (value instanceof URL ? value.href : value.url), location.href);
    return url.origin === location.origin || ((url.protocol === "http:" || url.protocol === "https:") && ["localhost", "127.0.0.1", "[::1]"].indexOf(url.hostname) !== -1 && !url.username && !url.password);
  }
  var originalFetch = window.fetch.bind(window);
  window.fetch = function (resource, options) {
    if (!permitted(resource)) return Promise.reject(new Error("Windows local mode blocks external requests. Use a local chat endpoint."));
    return originalFetch(resource, options);
  };
  var open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    if (!permitted(String(url))) throw new Error("Windows local mode blocks external uploads and requests.");
    return open.apply(this, arguments);
  };
  document.addEventListener("DOMContentLoaded", function () {
    document.title = "Windows Music Lab — Full Studio";
    var provider = document.getElementById("assistProvider");
    if (provider) {
      Array.from(provider.options).forEach(function (option) { if (/openrouter|cloud/i.test(option.value + " " + option.text)) option.disabled = option.hidden = true; });
      if (provider.selectedOptions.length && provider.selectedOptions[0].disabled) { var first = Array.from(provider.options).find(function(o) { return !o.disabled; }); if(first) provider.value = first.value; }
    }
    ["orKey", "orRemember", "orModel"].forEach(function(id){var el=document.getElementById(id);if(el)el.disabled=true;});
    var about = document.getElementById("aboutLogo");
    if (about) about.textContent = "Windows Music Lab";
  });
})();
