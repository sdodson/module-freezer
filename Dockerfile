FROM registry.access.redhat.com/ubi9/python-312:latest

WORKDIR /opt/app-root/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY module_freezer.py .

ENTRYPOINT ["python", "-u", "module_freezer.py"]
