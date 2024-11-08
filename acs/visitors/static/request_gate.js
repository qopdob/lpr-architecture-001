function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function sendGateRequest(event, gateId) {
    event.preventDefault();  // Prevent the default button action
    console.log('sendGateRequest called with gateId:', gateId);
    const csrftoken = getCookie('csrftoken');
    console.log('CSRF token:', csrftoken);
    
    $.ajax({
        url: `/admin/visitors/camera/request_gate/${gateId}/`,
        type: 'POST',
        headers: {'X-CSRFToken': csrftoken},
        success: function(response) {
            console.log('Success response:', response);
        },
        error: function(xhr, status, error) {
            console.log('Error:', error);
            console.log('Status:', status);
            console.log('XHR:', xhr);
            alert('An error occurred: ' + error);
        }
    });
    console.log('AJAX request sent');
}

// The document.ready function is no longer needed as we're using inline onclick

console.log('request_gate.js loaded');
