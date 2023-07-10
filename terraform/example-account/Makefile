entry: plan

init: config
	terraform init

init-upgrade:
	terraform init -upgrade=true

config:
	@if [[ ! -f local.ini ]]; then cp local.ini.dist local.ini; fi

plan: init
	terraform plan -var-file=local.ini

apply:
	terraform apply -var-file=local.ini

destroy-plan:
	terraform plan -destroy -var-file=local.ini

destroy:
	terraform destroy -var-file=local.ini

help:
	@echo ""
	@echo "[Available Make Commands:]"
	@echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
	@echo "make (make plan)"
	@echo "make plan (make init; terraform plan -var-file=local.ini)"
	@echo "make init (terraform init)"
	@echo "make init-upgrade (terraform init -upgrade=true)"
	@echo "make config (cp local.ini.dist local.ini)"
	@echo "make apply (terraform apply -var-file=local.ini"
	@echo "make destroy-plan (terraform plan -destroy -var-file=local.ini)"
	@echo "make destroy (terraform destroy -var-file=local.ini)"
	@echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
	@echo ""
