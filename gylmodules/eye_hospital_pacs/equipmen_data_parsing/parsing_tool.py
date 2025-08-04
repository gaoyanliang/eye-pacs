import xml.etree.ElementTree as ET


def parse_topcon_xml(xml_bytes):
    # Parse XML data with proper encoding handling

    try:
        xml_str = xml_bytes.decode('shift-jis')
    except UnicodeDecodeError:
        try:
            xml_str = xml_bytes.decode('cp932')
        except UnicodeDecodeError:
            xml_str = xml_bytes.decode('utf-8', errors='replace')  # Fallback

    # tree = ET.parse(BytesIO(xml_bytes))
    # root = tree.getroot()
    # Now parse the decoded string
    root = ET.fromstring(xml_str)

    # Define namespaces
    ns = {
        'nsCommon': 'http://www.joia.or.jp/standardized/namespaces/Common',
        'nsREF': 'http://www.joia.or.jp/standardized/namespaces/REF'
    }

    # Extract device information
    device_info = {
        'company': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}Company').text,
        'model': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}ModelName').text,
        'machine_no': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}MachineNo').text,
        'rom_version': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}ROMVersion').text,
        'version': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}Version').text,
        'date': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}Date').text,
        'time': root.find('.//{http://www.joia.or.jp/standardized/namespaces/Common}Time').text
    }

    # Extract eye data
    eye_data = {}

    # Right eye data
    r_median = root.find(
        './/{http://www.joia.or.jp/standardized/namespaces/REF}R/{http://www.joia.or.jp/standardized/namespaces/REF}Median')
    eye_data['right'] = {
        'sphere': float(r_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}Sphere').text),
        'cylinder': float(r_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}Cylinder').text),
        'axis': int(r_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}Axis').text),
        'SE': float(r_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}SE').text)
    }

    # Left eye data
    l_median = root.find(
        './/{http://www.joia.or.jp/standardized/namespaces/REF}L/{http://www.joia.or.jp/standardized/namespaces/REF}Median')
    eye_data['left'] = {
        'sphere': float(l_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}Sphere').text),
        'cylinder': float(l_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}Cylinder').text),
        'axis': int(l_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}Axis').text),
        'SE': float(l_median.find('{http://www.joia.or.jp/standardized/namespaces/REF}SE').text)
    }

    # Extract PD data
    pd_data = {
        'distance': float(root.find(
            './/{http://www.joia.or.jp/standardized/namespaces/REF}PD/{http://www.joia.or.jp/standardized/namespaces/REF}Distance').text),
        'near': float(root.find(
            './/{http://www.joia.or.jp/standardized/namespaces/REF}PD/{http://www.joia.or.jp/standardized/namespaces/REF}Near').text)
    }

    return {
        'device_info': device_info,
        'eye_data': eye_data,
        'pd_data': pd_data
    }


# Example usage
if __name__ == '__main__':
    # Read the file in binary mode
    with open('/Users/gaoyanliang/nsyy/nsyy-project/gylmodules/eye_hospital_pacs/equipmen_data_parsing/M-Serial3330_20250429_150051_TOPCON_RM-800_4694407.xml', 'rb') as f:
        xml_bytes = f.read()

    result = parse_topcon_xml(xml_bytes)

    print("Device Information:")
    print(f"Company: {result['device_info']['company']}")
    print(f"Model: {result['device_info']['model']}")
    print(f"Machine No: {result['device_info']['machine_no']}")
    print(f"ROM Version: {result['device_info']['rom_version']}")
    print(f"Software Version: {result['device_info']['version']}")
    print(f"Date: {result['device_info']['date']} {result['device_info']['time']}")
    # print(f"Time: {result['device_info']['time']}")

    print("\nRight Eye Average Values:")
    print(f"Sphere: {result['eye_data']['right']['sphere']} D")
    print(f"Cylinder: {result['eye_data']['right']['cylinder']} D")
    print(f"Axis: {result['eye_data']['right']['axis']}°")
    print(f"Spherical Equivalent (SE): {result['eye_data']['right']['SE']} D")

    print("\nLeft Eye Average Values:")
    print(f"Sphere: {result['eye_data']['left']['sphere']} D")
    print(f"Cylinder: {result['eye_data']['left']['cylinder']} D")
    print(f"Axis: {result['eye_data']['left']['axis']}°")
    print(f"Spherical Equivalent (SE): {result['eye_data']['left']['SE']} D")

    print("\nPupillary Distance (PD):")
    print(f"Distance PD: {result['pd_data']['distance']} mm")
    print(f"Near PD: {result['pd_data']['near']} mm")