import os
import re
import shutil

RELEASE_DIR = 'release'
TEMPLATES_DIR = os.path.join(RELEASE_DIR, 'templates')
CHARTS_DIR = os.path.join(RELEASE_DIR, 'charts')

values_dict = {
    "global": {
        "namespace": "clahanstore"
    }
}

def determine_chart_name(name, kind):
    # Global configs
    if kind in ['Namespace', 'StorageClass', 'Ingress', 'Gateway', 'HTTPRoute']:
        return 'global'
    if kind in ['Secret', 'ConfigMap'] and ('clahanstore' in name.lower() or 'secrets' in name.lower()):
        return 'global'
        
    if name == 'api-gateway' or name == 'frontend-ui' or name == 'mongodb':
        return name
        
    if name.endswith('-service'):
        return name
        
    if name.endswith('-deploy'):
        return name.replace('-deploy', '')
        
    if name.endswith('-hpa'):
        return name.replace('-hpa', '')

    return name

def write_to_template(chart_name, filename, content):
    if chart_name == "global":
        target_dir = TEMPLATES_DIR
        os.makedirs(target_dir, exist_ok=True)
    else:
        target_dir = os.path.join(CHARTS_DIR, chart_name, 'templates')
        os.makedirs(target_dir, exist_ok=True)
        
        # Ensure subchart has its own Chart.yaml
        chart_yaml_path = os.path.join(CHARTS_DIR, chart_name, 'Chart.yaml')
        if not os.path.exists(chart_yaml_path):
            with open(chart_yaml_path, 'w') as f:
                f.write(f"apiVersion: v2\nname: {chart_name}\ndescription: Helm subchart for {chart_name}\ntype: application\nversion: 0.1.0\nappVersion: \"1.0.0\"\n")
                
    with open(os.path.join(target_dir, filename), 'w') as f:
        f.write(content.strip() + '\n')

def process_file(filepath, filename_suffix=None):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath}, does not exist.")
        return
        
    with open(filepath, 'r') as f:
        content = f.read()

    content = '\n' + content
    docs = re.split(r'\n---', content)
        
    for doc in docs:
        doc = doc.strip()
        if not doc: continue
        
        name_match = re.search(r'^\s*name:\s*([^\s]+)', doc, re.MULTILINE)
        kind_match = re.search(r'^kind:\s*([^\s]+)', doc, re.MULTILINE)
        
        if not name_match or not kind_match:
            continue
            
        name = name_match.group(1).strip()
        kind = kind_match.group(1).strip()
        
        # Global namespace helmfication
        doc = re.sub(r'namespace:\s*clahanstore', 'namespace: {{ .Values.global.namespace }}', doc)
        doc = re.sub(r'namespace:\s*shopverse', 'namespace: {{ .Values.global.namespace }}', doc)
        
        target_chart = determine_chart_name(name, kind)
        
        if target_chart == 'global' and kind == 'Namespace':
            continue
            
        file_name = f"{name}-{kind.lower()}.yaml"
        if kind == 'Deployment' and filename_suffix == 'deploy':
            file_name = f"{name}-deploy.yaml"
        elif kind == 'Service' and (filename_suffix == 'service' or '-service' not in file_name):
            file_name = f"{name}-service.yaml"
        
        if target_chart != 'global':
            if kind in ['Deployment', 'StatefulSet']:
                if target_chart not in values_dict:
                    values_dict[target_chart] = {}
                    
                replicas_match = re.search(r'replicas:\s*(\d+)', doc)
                if replicas_match:
                    rep_count = int(replicas_match.group(1))
                    values_dict[target_chart]['replicas'] = rep_count
                    doc = re.sub(r'replicas:\s*\d+', f'replicas: {{{{ .Values.replicas }}}}', doc)
                else:
                    values_dict[target_chart]['replicas'] = 1
                    
                # Replace image logic
                for line in doc.split('\n'):
                    if 'image:' in line and 'busybox' not in line:
                        img_match = re.search(r'image:\s*([^\s:]+)(?::([^\s]+))?', line)
                        if img_match:
                            repo = img_match.group(1)
                            tag = img_match.group(2) if img_match.group(2) else "latest"
                            values_dict[target_chart]['image'] = {'repository': repo, 'tag': tag}
                            original_img_str = line.strip()
                            new_img_str = f"image: {{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}"
                            doc = doc.replace(original_img_str, new_img_str)
                        break
                
                # MongoDB storage class customization
                if name == 'mongodb' and kind == 'StatefulSet':
                    doc = re.sub(r'storageClassName:\s*[^\s]+', 'storageClassName: nfs-client', doc)
                    if 'storageClassName' not in doc and 'volumeClaimTemplates' in doc:
                        doc = doc.replace('accessModes:', 'storageClassName: nfs-client\n        accessModes:')
                        
        write_to_template(target_chart, file_name, doc)
        print(f"Created {file_name} in [{target_chart}] chart")

def main():
    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR)
        
    os.makedirs(RELEASE_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(CHARTS_DIR, exist_ok=True)
    
    # Process all k8s files
    process_file(os.path.join('kubernetes', 'deployments', 'all-deployments.yaml'), 'deploy')
    process_file(os.path.join('kubernetes', 'services', 'all-services.yaml'), 'service')
    # Try both cases for config
    process_file(os.path.join('kubernetes', 'configmaps', 'ClahanStore-config.yaml'))
    process_file(os.path.join('kubernetes', 'configmaps', 'clahanstore-config.yaml'))
    process_file(os.path.join('kubernetes', 'configmaps', 'secrets.yaml'))
    process_file(os.path.join('kubernetes', 'hpa', 'all-hpa.yaml'))
    process_file(os.path.join('kubernetes', 'deployments', 'mongodb-statefulset.yaml'))
    process_file(os.path.join('kubernetes', 'ingress', 'kgateway-routes.yaml'))
    process_file(os.path.join('kubernetes', 'services', 'nfs-storageclass.yaml'))
    
    chart_yaml = """apiVersion: v2
name: ecommerce-application
description: Umbrella Helm chart for the E-Commerce microservices application
type: application
version: 0.1.0
appVersion: "1.0.0"
"""
    with open(os.path.join(RELEASE_DIR, 'Chart.yaml'), 'w') as f:
        f.write(chart_yaml)
        
    def build_yaml(d, indent=0):
        result = ""
        for k, v in d.items():
            if isinstance(v, dict):
                result += " " * indent + f"{k}:\n"
                result += build_yaml(v, indent + 2)
            else:
                if isinstance(v, str) and not v.startswith('"'):
                    result += " " * indent + f"{k}: \"{v}\"\n"
                else:
                    result += " " * indent + f"{k}: {v}\n"
        return result
        
    with open(os.path.join(RELEASE_DIR, 'values.yaml'), 'w') as f:
        f.write(build_yaml(values_dict))
    
    namespace_yaml = """apiVersion: v1
kind: Namespace
metadata:
  name: {{ .Values.global.namespace }}
"""
    with open(os.path.join(TEMPLATES_DIR, 'namespace-auto-create.yaml'), 'w') as f:
        f.write(namespace_yaml)
        
    print("Umbrella Helm chart parameterized and generated successfully in 'release/' directory.")

if __name__ == '__main__':
    main()
