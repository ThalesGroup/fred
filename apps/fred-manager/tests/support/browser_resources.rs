// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Metadata only, in the disposable browser database. Not a production route or import format.
use fred_manager::{
    db,
    domain::{Document, Folder},
    fga::Fga,
    keycloak::Directory,
};
use sqlx::PgPool;
use uuid::Uuid;

pub fn router(pool: PgPool, fga: Fga, directory: Directory) -> axum::Router {
    axum::Router::new().route("/test-fixture/resources", axum::routing::post(move || {
        let (pool, fga, directory) = (pool.clone(), fga.clone(), directory.clone());
        async move {
            let priya = directory.find_username("priya").await.unwrap().unwrap();
            let memberships = fred_manager::spaces::memberships(&pool, &fga, &priya.id).await.unwrap();
            let team = memberships.iter().find(|m| m.space.name == "fredlab").unwrap().space.id;
            let personal = memberships.iter().find(|m| m.space.personal_owner.as_deref() == Some(&priya.id)).unwrap().space.id;
            let folder = Folder { created_at: chrono::Utc::now(), id: Uuid::new_v4(), space_id: team, parent_id: None, name:"Library".into(), path:String::new() };
            let folder = Folder {path:format!("/{}/",folder.id),..folder};
            db::insert_folder(&pool,&folder).await.unwrap();
            let empty = Folder {created_at: chrono::Utc::now(),id:Uuid::new_v4(),space_id:team,parent_id:Some(folder.id),name:"Empty".into(),path:String::new()};
            let empty = Folder {path:format!("{}{}/",folder.path,empty.id),..empty};
            db::insert_folder(&pool,&empty).await.unwrap();
            for i in 0..55 {
                let (space_id,folder_id,name) = match i {
                    53 => (personal,None,"Priya private.txt".into()),
                    54 => (team,None,"Team root.txt".into()),
                    _ => (team,Some(folder.id),format!("Document {:02}.txt",i)),
                };
                crate::environment::insert_document(&pool,&Document {id:Uuid::new_v4(),space_id,folder_id,name,mime:"text/plain".into(),size:42,sha256:format!("{i:064x}"),created_by:priya.id.clone(),created_at:chrono::Utc::now()}).await.unwrap();
            }
            axum::Json(serde_json::json!({"team":team,"personal":personal,"folder":folder.id,"empty":empty.id}))
        }
    }))
}
