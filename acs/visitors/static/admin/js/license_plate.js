function setupLicensePlate(widgetName, plateType, parts) {
    const licensePlate = document.getElementById(`license-plate-${widgetName}`);
    if (!licensePlate) {
        console.error(`License plate element not found for widget: ${widgetName}`);
        return;
    }

    // Clear existing classes
    licensePlate.className = 'license-plate';

    // Add plate type class
    licensePlate.classList.add(plateType);

    const part1 = document.getElementById(`part1-${widgetName}`);
    const part2 = document.getElementById(`part2-${widgetName}`);
    const part3 = document.getElementById(`part3-${widgetName}`);
    const region = document.getElementById(`region-${widgetName}`);

    if (!part1 || !part2 || !part3 || !region) {
        console.error(`One or more elements not found for widget: ${widgetName}`);
        return;
    }

    // Set content and handle 3-digit region
    switch (plateType) {
        case 'car':
            part1.textContent = parts[0];
            part2.textContent = parts[1];
            part3.textContent = parts[2];
            region.textContent = parts[3];
            break;
        case 'public':
            part1.textContent = parts[0];
            part2.textContent = parts[1];
            part3.textContent = '';
            region.textContent = parts[2];
            break;
        case 'military':
            part1.textContent = parts[0];
            part2.textContent = parts[1];
            part3.textContent = '';
            region.textContent = parts[2];
            break;
        case 'diplomatic':
            part1.textContent = parts[0];
            part2.textContent = parts[1];
            part3.textContent = parts[2];
            region.textContent = parts[3];
            break;
        case 'police':
            part1.textContent = parts[0];
            part2.textContent = parts[1];
            part3.textContent = '';
            region.textContent = parts[2];
            break;
    }

    // Add three-digit class if region has 3 digits
    if (region.textContent.length === 3) {
        licensePlate.classList.add('three-digit');
    }
}

